"""Load the opening product list and opening stock from a spreadsheet (CSV), all or nothing.

    python manage.py import_catalog --file products.csv --user owner [--dry-run]

Columns (header row required; template: docs/onboarding/catalog-template.csv):
  section            Section name or code: Clothing / Printing / Photography
  name               Product or service name. Rows with the same section + name become one
                     product with size/colour options.
  kind               product (default) or service
  category           Optional; created if new
  sku                Optional product code
  size, color        Optional option values (leave both empty for a product without options)
  selling_price      Selling price in USD (the reporting base)
  buying_price       Optional reference buying price in USD
  minimum_stock      Low-stock alert level (default 0)
  opening_quantity   Units on hand now (default 0). Recorded as "Opening stock".
  opening_unit_cost  USD cost per unit for the opening stock (defaults to buying_price)

Rules: nothing is saved if any row has a problem; every problem is listed with its line number.
Products that already exist are refused (add their stock from the Inventory screen instead).
"""

import csv
from collections import OrderedDict
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models import Category, Product, ProductVariant
from apps.identity.models import Membership
from apps.inventory.models import StockAdjustment
from apps.inventory.services import adjust_stock
from apps.organizations.models import Organization

COLUMNS = (
    "section",
    "name",
    "kind",
    "category",
    "sku",
    "size",
    "color",
    "selling_price",
    "buying_price",
    "minimum_stock",
    "opening_quantity",
    "opening_unit_cost",
)


class RowError(Exception):
    pass


def _decimal(row, column, default=None, *, minimum=Decimal("0")):
    raw = (row.get(column) or "").strip().replace(",", "")
    if not raw:
        if default is None:
            raise RowError(f"{column} is required")
        return default
    try:
        value = Decimal(raw)
    except InvalidOperation:
        raise RowError(f"{column} '{raw}' is not a number") from None
    if value < minimum:
        raise RowError(f"{column} cannot be negative")
    return value


class Command(BaseCommand):
    help = "Import the opening product catalog and opening stock from a CSV file (all or nothing)."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True)
        parser.add_argument("--user", required=True, help="Username of the owner/admin recording the opening stock")
        parser.add_argument("--organization", help="Organization name (needed only if there is more than one)")
        parser.add_argument("--branch", help="Branch code for opening stock (needed only if there is more than one)")
        parser.add_argument("--dry-run", action="store_true", help="Check the file and report, without saving anything")

    def handle(self, *args, **options):
        organization = self._organization(options.get("organization"))
        actor = self._actor(organization, options["user"])
        branch = self._branch(organization, options.get("branch"))
        sections = {s.code.lower(): s for s in organization.sections.all()} | {s.name.lower(): s for s in organization.sections.all()}

        try:
            with open(options["file"], newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
                header = [h.strip().lower() for h in (rows[0].keys() if rows else [])]
        except FileNotFoundError:
            raise CommandError(f"File not found: {options['file']}") from None
        if not rows:
            raise CommandError("The file has no rows under the header.")
        missing = [c for c in ("section", "name", "selling_price") if c not in header]
        if missing:
            raise CommandError(f"Missing required column(s): {', '.join(missing)}. Expected: {', '.join(COLUMNS)}")

        products, errors = OrderedDict(), []
        for number, raw in enumerate(rows, start=2):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
            if not any(row.values()):
                continue
            try:
                section = sections.get(row.get("section", "").lower())
                if section is None:
                    raise RowError(f"unknown section '{row.get('section')}' (use {', '.join(s.name for s in organization.sections.all())})")
                name = row.get("name", "")
                if not name:
                    raise RowError("name is required")
                kind = (row.get("kind") or "product").lower()
                if kind not in ("product", "service"):
                    raise RowError("kind must be product or service")
                option = {
                    "size": row.get("size", ""),
                    "color": row.get("color", ""),
                    "quantity": _decimal(row, "opening_quantity", Decimal("0")),
                }
                buying = _decimal(row, "buying_price", Decimal("0"))
                option["unit_cost"] = _decimal(row, "opening_unit_cost", buying)
                if kind == "service" and option["quantity"]:
                    raise RowError("services cannot have opening stock")
                if option["quantity"] and not option["unit_cost"]:
                    raise RowError("opening stock needs opening_unit_cost (or buying_price)")
                key = (section.pk, name.lower())
                product = products.setdefault(
                    key,
                    {
                        "line": number,
                        "section": section,
                        "name": name,
                        "kind": kind,
                        "category": row.get("category", ""),
                        "sku": row.get("sku", ""),
                        "selling": _decimal(row, "selling_price"),
                        "buying": buying,
                        "minimum": _decimal(row, "minimum_stock", Decimal("0")),
                        "options": [],
                    },
                )
                if any((o["size"], o["color"]) == (option["size"], option["color"]) for o in product["options"]):
                    raise RowError(f"duplicate size/colour for {name}")
                product["options"].append({**option, "line": number})
                if Product.objects.filter(organization=organization, section=section, name__iexact=name).exists():
                    raise RowError(f"'{name}' is already in the catalog; add its stock from the Inventory screen")
                if product["sku"] and Product.objects.filter(organization=organization, sku__iexact=product["sku"]).exists():
                    raise RowError(f"SKU '{product['sku']}' is already used")
            except RowError as exc:
                errors.append(f"line {number}: {exc}")
        skus = [p["sku"].lower() for p in products.values() if p["sku"]]
        for sku in {s for s in skus if skus.count(s) > 1}:
            errors.append(f"SKU '{sku}' appears on more than one product in the file")

        if errors:
            self.stderr.write(self.style.ERROR(f"Nothing was imported. Fix these {len(errors)} problem(s) and run again:"))
            for error in errors:
                self.stderr.write(f"  {error}")
            raise SystemExit(1)

        units = sum(o["quantity"] for p in products.values() for o in p["options"])
        value = sum(o["quantity"] * o["unit_cost"] for p in products.values() for o in p["options"])
        summary = f"{len(products)} products, {sum(len(p['options']) for p in products.values())} size/colour lines, {units.normalize():f} units of opening stock worth USD {value:,.2f}"
        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"Dry run OK: {summary}. Nothing was saved."))
            return

        with transaction.atomic():
            for p in products.values():
                category = None
                if p["category"]:
                    category, _ = Category.objects.get_or_create(organization=organization, name=p["category"])
                product = Product.objects.create(
                    organization=organization,
                    section=p["section"],
                    category=category,
                    name=p["name"],
                    sku=p["sku"],
                    kind=p["kind"],
                    tracks_stock=p["kind"] == "product",
                    selling_price_base=p["selling"],
                    buying_price_base=p["buying"],
                    minimum_stock=p["minimum"],
                )
                if p["kind"] == "service":
                    continue
                for option in p["options"]:
                    has_options = option["size"] or option["color"]
                    code = slugify(f"{option['size']}-{option['color']}".strip("-"))[:80] if has_options else "default"
                    variant = ProductVariant.objects.create(
                        product=product, code=code or "default", size=option["size"], color=option["color"]
                    )
                    if option["quantity"] > 0:
                        adjust_stock(
                            organization=organization,
                            variant=variant,
                            branch=branch,
                            quantity_delta=option["quantity"],
                            reason=StockAdjustment.Reason.OPENING,
                            actor=actor,
                            unit_cost_base=option["unit_cost"],
                            note="Imported opening stock",
                        )
        self.stdout.write(self.style.SUCCESS(f"Imported {summary}."))

    def _organization(self, name):
        organizations = Organization.objects.filter(active=True)
        if name:
            organizations = organizations.filter(name__iexact=name)
        if organizations.count() != 1:
            raise CommandError("Name the organization with --organization." if not name else f"Organization '{name}' not found.")
        return organizations.get()

    def _actor(self, organization, username):
        user = get_user_model().objects.filter(username=username).first()
        membership = (
            Membership.objects.filter(organization=organization, user=user, active=True).select_related("role").first() if user else None
        )
        if membership is None or not membership.role.permissions.filter(code="inventory.adjust").exists():
            raise CommandError(f"'{username}' must be an active member allowed to adjust inventory (an owner/admin or manager).")
        return user

    def _branch(self, organization, code):
        branches = organization.branches.filter(active=True)
        if code:
            branches = branches.filter(code=code)
        if branches.count() != 1:
            raise CommandError("Name the branch with --branch <code>." if not code else f"Branch '{code}' not found.")
        return branches.get()
