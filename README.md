# Payment Reconciliation Automation

A Python automation agent that reconciles invoice records against bank transfer statements, flags discrepancies, and generates structured exception reports.

---

## What It Does

Manual payment reconciliation — matching hundreds of invoices against bank statements — is time-consuming and error-prone. This agent automates the entire workflow:

1. Accepts a ZIP file containing invoice CSVs and a month-end bank statement
2. Parses and standardizes all records
3. Matches transactions using a two-tier logic (exact reference → fuzzy amount + date)
4. Flags unmatched records and amount discrepancies as exceptions
5. Outputs a full reconciliation report and a focused exception report

---

## How It Works

```
ZIP Input
├── invoice_january.csv
├── invoice_february.csv
└── bank_statement_q1.csv
        │
        ▼
┌─────────────────────┐
│   Extract & Parse   │  Read all CSVs, standardize columns and data types
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│   Match Records     │  Priority 1: Exact Reference ID match
│                     │  Priority 2: Fuzzy Amount + Date match (±3 days, ±0.01)
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│   Flag Exceptions   │  Unmatched invoices, unmatched bank transactions,
│                     │  and amount discrepancies are flagged ⚠
└────────┬────────────┘
         │
         ▼
CSV Output
├── reconciliation_report_YYYYMMDD.csv   ← Full record of all matches
└── exception_report_YYYYMMDD.csv        ← Exceptions only, for manual review
```

---

## Requirements

- Python 3.8+
- pandas

Install dependencies:

```bash
pip install pandas
```

---

## Usage

```bash
python reconciliation.py --zip your_file.zip
```

Optional: specify output directory

```bash
python reconciliation.py --zip your_file.zip --output ./reports
```

---

## Input Format

Your ZIP file must contain:

**Invoice CSV(s)** — filename must include the word `invoice`

| Reference ID | Invoice Date | Amount  | Vendor Name     |
|-------------|-------------|---------|-----------------|
| INV-1042    | 2024-01-05  | 1500.00 | Acme Corp       |
| INV-1043    | 2024-01-08  | 800.00  | Global Supplies |

**Bank Statement CSV** — filename must include `bank` or `statement`

| Reference   | Transaction Date | Debit Amount |
|-------------|-----------------|-------------|
| INV-1042    | 2024-01-05      | 1500.00     |
| TXN-8821    | 2024-01-09      | 800.00      |

> **Note:** Column names can be customized in the `COLUMN MAPPING` section at the top of `reconciliation.py`.

---

## Output

**reconciliation_report.csv** — complete record of all transactions

| Invoice Reference | Vendor | Invoice Date | Invoice Amount | Bank Reference | Bank Date | Bank Amount | Match Status | Amount Difference | Flag |
|---|---|---|---|---|---|---|---|---|---|
| INV-1042 | Acme Corp | 2024-01-05 | 1500.00 | INV-1042 | 2024-01-05 | 1500.00 | Exact Reference Match | 0.00 | |
| INV-1043 | Global Supplies | 2024-01-08 | 800.00 | TXN-8821 | 2024-01-09 | 800.00 | Fuzzy Match (Amount + Date) | 0.00 | |

**exception_report.csv** — exceptions only, for manual review

---

## Sample Console Output

```
[1/5] Extracting ZIP file...
[2/5] Identifying invoice and bank statement files...
      Found 2 invoice file(s) and 1 bank statement.
[3/5] Loading and parsing records...
      47 invoice records | 51 bank transactions
[4/5] Matching records...
[5/5] Generating reports...

============================================================
       PAYMENT RECONCILIATION — SUMMARY
============================================================
  Total Records Processed : 54
  Matched                 : 49
  Exceptions Flagged      : 5
  Match Rate              : 90.7%
------------------------------------------------------------
  Full Report      → ./reports/reconciliation_report_20240131.csv
  Exception Report → ./reports/exception_report_20240131.csv
============================================================
```

---

## Matching Logic

| Priority | Method | Condition |
|---|---|---|
| 1 | Exact Reference Match | Reference IDs match exactly |
| 2 | Fuzzy Match | Amount within ±0.01 AND date within ±3 days |
| — | Exception | No match found → flagged ⚠ |

Amount tolerance and date window can be adjusted at the top of `reconciliation.py`.

---

## Built With

- Python 3.x
- pandas

---

## Author

**Jahin Afsan**  
BBA, Finance — Institute of Business Administration, University of Dhaka  
[LinkedIn](https://linkedin.com/in/jahinafsan) · [GitHub](https://github.com/jahinafsan07)
