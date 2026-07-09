"""Load classic Northwind sample data into the InsightRAG warehouse schema."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# Classic Northwind order range (830 orders, ~2.1k line items).
_ORDER_ID_MIN = 10248
_ORDER_ID_MAX = 11077

_SOURCE_DB = Path(__file__).resolve().parents[1] / "data" / "warehouse" / "northwind_source.db"


def _parse_date(value: str | None, fallback: str = "1996-07-04") -> str:
    if not value:
        return fallback
    text = str(value).strip()
    if " " in text:
        text = text.split(" ")[0]
    if "T" in text:
        text = text.split("T")[0]
    return text[:10]


def _order_status(shipped_date: str | None) -> str:
    if not shipped_date:
        return "cancelled"
    return "delivered"


def load_northwind_data(source_path: Path | None = None) -> dict[str, list[tuple]]:
    path = source_path or _SOURCE_DB
    if not path.exists():
        raise FileNotFoundError(
            f"Northwind source database not found at {path}. "
            "Run: curl -fsSL -o data/warehouse/northwind_source.db "
            "https://github.com/jpwhite3/northwind-SQLite3/raw/main/dist/northwind.db"
        )

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT CustomerID, CompanyName, Region, Country
            FROM Customers
            ORDER BY CustomerID
            """
        )
        customer_rows = cur.fetchall()
        customer_id_map: dict[str, int] = {}
        customers: list[tuple] = []
        for idx, row in enumerate(customer_rows, start=1):
            customer_id_map[row["CustomerID"]] = idx
            region = (row["Region"] or row["Country"] or "Unknown").strip()
            customers.append((idx, row["CompanyName"], region, "1994-01-15"))

        cur.execute(
            """
            SELECT p.ProductID, p.ProductName, c.CategoryName, p.UnitPrice
            FROM Products p
            JOIN Categories c ON p.CategoryID = c.CategoryID
            ORDER BY p.ProductID
            """
        )
        products = [
            (r["ProductID"], r["ProductName"], r["CategoryName"], float(r["UnitPrice"]))
            for r in cur.fetchall()
        ]

        cur.execute(
            f"""
            SELECT OrderID, CustomerID, OrderDate, ShippedDate, ShipVia
            FROM Orders
            WHERE OrderID BETWEEN {_ORDER_ID_MIN} AND {_ORDER_ID_MAX}
            ORDER BY OrderID
            """
        )
        order_rows = cur.fetchall()
        orders: list[tuple] = []
        for row in order_rows:
            cid = customer_id_map.get(row["CustomerID"])
            if cid is None:
                continue
            orders.append(
                (
                    row["OrderID"],
                    cid,
                    _parse_date(row["OrderDate"]),
                    _order_status(row["ShippedDate"]),
                )
            )

        cur.execute(
            f"""
            SELECT od.rowid, od.OrderID, od.ProductID, od.Quantity, od.UnitPrice
            FROM "Order Details" od
            JOIN Orders o ON od.OrderID = o.OrderID
            WHERE o.OrderID BETWEEN {_ORDER_ID_MIN} AND {_ORDER_ID_MAX}
            ORDER BY od.rowid
            """
        )
        order_items = [
            (
                r["rowid"],
                r["OrderID"],
                r["ProductID"],
                int(r["Quantity"]),
                float(r["UnitPrice"]),
            )
            for r in cur.fetchall()
        ]

        cur.execute("SELECT ShipperID, CompanyName FROM Shippers")
        shipper_map = {r["ShipperID"]: r["CompanyName"] for r in cur.fetchall()}

        shipments: list[tuple] = []
        ship_id = 1
        for row in order_rows:
            if not row["ShippedDate"]:
                continue
            shipped = _parse_date(row["ShippedDate"])
            delivered_dt = datetime.strptime(shipped, "%Y-%m-%d") + timedelta(days=3)
            carrier = shipper_map.get(row["ShipVia"], "Unknown Carrier")
            shipments.append(
                (
                    ship_id,
                    row["OrderID"],
                    carrier,
                    shipped,
                    delivered_dt.date().isoformat(),
                    "delivered",
                )
            )
            ship_id += 1

        return {
            "customers": customers,
            "products": products,
            "orders": orders,
            "order_items": order_items,
            "shipments": shipments,
        }
    finally:
        conn.close()
