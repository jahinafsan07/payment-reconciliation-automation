"""
Payment Reconciliation Automation
----------------------------------
Matches invoice records against bank transfer statements,
flags discrepancies, and generates an exception report.

Usage:
    python reconciliation.py --zip invoices_and_statement.zip

Input ZIP must contain:
    - One or more invoice CSV files (filename contains 'invoice')
    - One bank statement CSV file (filename contains 'bank' or 'statement')

Output:
    - reconciliation_report.csv  (full matched + unmatched records)
    - exception_report.csv       (discrepancies only)
"""

import os
import sys
import zipfile
import argparse
import pandas as pd
from datetime import datetime


# ── Configuration ─────────────────────────────────────────────────────────────

MATCH_TOLERANCE = 0.01          # Amount tolerance for fuzzy matching (e.g. rounding differences)
DATE_WINDOW_DAYS = 3            # Number of days within which dates are considered a match
INVOICE_KEYWORD = "invoice"     # Keyword to identify invoice files in the ZIP
BANK_KEYWORD = ["bank", "statement"]  # Keywords to identify bank statement file


# ── Column Mapping ────────────────────────────────────────────────────────────
# Adjust these to match your actual CSV column names

INVOICE_COLUMNS = {
    "reference": "Reference ID",   # Unique invoice reference number
    "date":      "Invoice Date",   # Date of invoice
    "amount":    "Amount",         # Invoice amount
    "vendor":    "Vendor Name",    # Vendor / payee name
}

BANK_COLUMNS = {
    "reference": "Reference",      # Bank transaction reference
    "date":      "Transaction Date",
    "amount":    "Debit Amount",   # Column for outgoing payments
}


# ── Helper Functions ──────────────────────────────────────────────────────────

def extract_zip(zip_path: str, extract_to: str) -> list[str]:
    """Extract ZIP file and return list of extracted file paths."""
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(extract_to)
        return [os.path.join(extract_to, name) for name in z.namelist()]


def identify_files(file_paths: list[str]) -> tuple[list[str], str]:
    """Separate invoice files from bank statement file."""
    invoice_files = []
    bank_file = None

    for path in file_paths:
        name = os.path.basename(path).lower()
        if any(kw in name for kw in BANK_KEYWORD):
            bank_file = path
        elif INVOICE_KEYWORD in name and path.endswith(".csv"):
            invoice_files.append(path)

    if not invoice_files:
        raise FileNotFoundError("No invoice CSV files found in ZIP. Ensure filenames contain 'invoice'.")
    if not bank_file:
        raise FileNotFoundError("No bank statement CSV found in ZIP. Ensure filename contains 'bank' or 'statement'.")

    return invoice_files, bank_file


def load_invoices(invoice_files: list[str]) -> pd.DataFrame:
    """Load and combine all invoice CSVs into a single DataFrame."""
    frames = []
    for path in invoice_files:
        df = pd.read_csv(path)
        df.columns = df.columns.str.strip()
        frames.append(df)
    invoices = pd.concat(frames, ignore_index=True)

    # Rename to standard internal column names
    invoices = invoices.rename(columns={
        INVOICE_COLUMNS["reference"]: "inv_reference",
        INVOICE_COLUMNS["date"]:      "inv_date",
        INVOICE_COLUMNS["amount"]:    "inv_amount",
        INVOICE_COLUMNS["vendor"]:    "vendor",
    })

    invoices["inv_date"] = pd.to_datetime(invoices["inv_date"], dayfirst=True, errors="coerce")
    invoices["inv_amount"] = pd.to_numeric(invoices["inv_amount"], errors="coerce")
    invoices["inv_reference"] = invoices["inv_reference"].astype(str).str.strip().str.upper()
    return invoices


def load_bank_statement(bank_file: str) -> pd.DataFrame:
    """Load bank statement CSV into a DataFrame."""
    bank = pd.read_csv(bank_file)
    bank.columns = bank.columns.str.strip()

    bank = bank.rename(columns={
        BANK_COLUMNS["reference"]: "bank_reference",
        BANK_COLUMNS["date"]:      "bank_date",
        BANK_COLUMNS["amount"]:    "bank_amount",
    })

    bank["bank_date"] = pd.to_datetime(bank["bank_date"], dayfirst=True, errors="coerce")
    bank["bank_amount"] = pd.to_numeric(bank["bank_amount"], errors="coerce")
    bank["bank_reference"] = bank["bank_reference"].astype(str).str.strip().str.upper()
    return bank


def match_records(invoices: pd.DataFrame, bank: pd.DataFrame) -> pd.DataFrame:
    """
    Attempt to match each invoice against a bank transaction.
    Matching logic (in order of priority):
        1. Exact reference ID match
        2. Fuzzy match: amount within tolerance + date within window
    """
    results = []
    bank_used = set()  # Track bank rows already matched

    for _, inv_row in invoices.iterrows():
        matched = False
        match_type = None
        bank_row_data = {}

        # --- Priority 1: Exact Reference Match ---
        ref_matches = bank[
            (bank["bank_reference"] == inv_row["inv_reference"]) &
            (~bank.index.isin(bank_used))
        ]

        if not ref_matches.empty:
            b = ref_matches.iloc[0]
            amount_diff = abs(inv_row["inv_amount"] - b["bank_amount"])
            date_diff = abs((inv_row["inv_date"] - b["bank_date"]).days) if pd.notnull(inv_row["inv_date"]) and pd.notnull(b["bank_date"]) else 999

            if amount_diff <= MATCH_TOLERANCE:
                matched = True
                match_type = "Exact Reference Match"
            elif amount_diff > MATCH_TOLERANCE:
                matched = True
                match_type = f"Reference Match — Amount Discrepancy (Δ {amount_diff:.2f})"
            
            if matched:
                bank_used.add(ref_matches.index[0])
                bank_row_data = b.to_dict()

        # --- Priority 2: Fuzzy Amount + Date Match ---
        if not matched:
            fuzzy_matches = bank[
                (abs(bank["bank_amount"] - inv_row["inv_amount"]) <= MATCH_TOLERANCE) &
                (~bank.index.isin(bank_used))
            ]
            if not fuzzy_matches.empty and pd.notnull(inv_row["inv_date"]):
                fuzzy_matches = fuzzy_matches.copy()
                fuzzy_matches["date_diff"] = fuzzy_matches["bank_date"].apply(
                    lambda d: abs((inv_row["inv_date"] - d).days) if pd.notnull(d) else 999
                )
                fuzzy_matches = fuzzy_matches[fuzzy_matches["date_diff"] <= DATE_WINDOW_DAYS]
                if not fuzzy_matches.empty:
                    best = fuzzy_matches.sort_values("date_diff").iloc[0]
                    matched = True
                    match_type = "Fuzzy Match (Amount + Date)"
                    bank_used.add(best.name)
                    bank_row_data = best.to_dict()

        # --- Build result row ---
        result = {
            "Invoice Reference":    inv_row.get("inv_reference", ""),
            "Vendor":               inv_row.get("vendor", ""),
            "Invoice Date":         inv_row["inv_date"].strftime("%Y-%m-%d") if pd.notnull(inv_row["inv_date"]) else "",
            "Invoice Amount":       inv_row["inv_amount"],
            "Bank Reference":       bank_row_data.get("bank_reference", "NOT FOUND"),
            "Bank Date":            bank_row_data["bank_date"].strftime("%Y-%m-%d") if bank_row_data.get("bank_date") and pd.notnull(bank_row_data["bank_date"]) else "",
            "Bank Amount":          bank_row_data.get("bank_amount", ""),
            "Match Status":         match_type if matched else "UNMATCHED",
            "Amount Difference":    round(abs(inv_row["inv_amount"] - bank_row_data.get("bank_amount", 0)), 2) if matched else inv_row["inv_amount"],
            "Flag":                 "" if (matched and "Discrepancy" not in str(match_type)) else "⚠ EXCEPTION",
        }
        results.append(result)

    # --- Unmatched bank transactions (payments with no invoice) ---
    for idx, b_row in bank.iterrows():
        if idx not in bank_used:
            result = {
                "Invoice Reference":    "NO INVOICE",
                "Vendor":               "",
                "Invoice Date":         "",
                "Invoice Amount":       "",
                "Bank Reference":       b_row["bank_reference"],
                "Bank Date":            b_row["bank_date"].strftime("%Y-%m-%d") if pd.notnull(b_row["bank_date"]) else "",
                "Bank Amount":          b_row["bank_amount"],
                "Match Status":         "UNMATCHED BANK TRANSACTION",
                "Amount Difference":    b_row["bank_amount"],
                "Flag":                 "⚠ EXCEPTION",
            }
            results.append(result)

    return pd.DataFrame(results)


def generate_reports(report: pd.DataFrame, output_dir: str):
    """Save full reconciliation report and exception-only report."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    full_path = os.path.join(output_dir, f"reconciliation_report_{timestamp}.csv")
    exception_path = os.path.join(output_dir, f"exception_report_{timestamp}.csv")

    report.to_csv(full_path, index=False)

    exceptions = report[report["Flag"] == "⚠ EXCEPTION"]
    exceptions.to_csv(exception_path, index=False)

    return full_path, exception_path, len(exceptions)


def print_summary(report: pd.DataFrame, full_path: str, exception_path: str, exception_count: int):
    """Print a clean summary to the console."""
    total = len(report)
    matched = len(report[~report["Flag"].str.contains("EXCEPTION", na=False)])
    match_rate = round((matched / total) * 100, 1) if total > 0 else 0

    print("\n" + "="*60)
    print("       PAYMENT RECONCILIATION — SUMMARY")
    print("="*60)
    print(f"  Total Records Processed : {total}")
    print(f"  Matched                 : {matched}")
    print(f"  Exceptions Flagged      : {exception_count}")
    print(f"  Match Rate              : {match_rate}%")
    print("-"*60)
    print(f"  Full Report   → {full_path}")
    print(f"  Exception Report → {exception_path}")
    print("="*60 + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Payment Reconciliation Automation Agent")
    parser.add_argument("--zip", required=True, help="Path to ZIP file containing invoices and bank statement")
    parser.add_argument("--output", default=".", help="Directory to save output reports (default: current directory)")
    args = parser.parse_args()

    if not os.path.exists(args.zip):
        print(f"Error: ZIP file not found at '{args.zip}'")
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)
    extract_dir = os.path.join(args.output, "extracted")
    os.makedirs(extract_dir, exist_ok=True)

    print("\n[1/5] Extracting ZIP file...")
    file_paths = extract_zip(args.zip, extract_dir)

    print("[2/5] Identifying invoice and bank statement files...")
    invoice_files, bank_file = identify_files(file_paths)
    print(f"      Found {len(invoice_files)} invoice file(s) and 1 bank statement.")

    print("[3/5] Loading and parsing records...")
    invoices = load_invoices(invoice_files)
    bank = load_bank_statement(bank_file)
    print(f"      {len(invoices)} invoice records | {len(bank)} bank transactions")

    print("[4/5] Matching records...")
    report = match_records(invoices, bank)

    print("[5/5] Generating reports...")
    full_path, exception_path, exception_count = generate_reports(report, args.output)

    print_summary(report, full_path, exception_path, exception_count)


if __name__ == "__main__":
    main()
