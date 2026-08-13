"""
PDF extraction utilities for NTC Sri Lanka statistical report tables.

Handles the source PDFs' specific quirks: tables laid out with whitespace
alignment instead of ruling lines, row labels wrapping across 2-3 physical
lines, and numbers occasionally split by pdfplumber's column detection.
"""

import re
import pdfplumber
import pandas as pd


def find_page_by_marker(pdf_path, marker_text):
    """
    Search every page for a unique, row-level marker string (not a table
    title, which false-positives on the Table of Contents). Returns a
    list of matching page indices.
    """
    matches = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if marker_text in text:
                matches.append(i)
    return matches


def extract_numbers(line):
    """Pull every number-looking token out of a line of text."""
    return re.findall(r'-?\d[\d,]*\.?\d*', line)


def merge_split_decimals(numbers):
    """Fix decimals torn into two tokens, e.g. '5594.' + '48' -> '5594.48'."""
    merged, skip = [], False
    for idx, num in enumerate(numbers):
        if skip:
            skip = False
            continue
        if num.endswith('.') and idx + 1 < len(numbers) and re.fullmatch(r'\d{1,2}', numbers[idx + 1]):
            merged.append(num + numbers[idx + 1])
            skip = True
        else:
            merged.append(num)
    return merged


def is_furniture(line, extra_keywords=None):
    """Identify page furniture: titles, source lines, headers, page numbers."""
    keywords = ["Figure", "Table 5.", "Table 6.", "Source:", "Item ", "Operational Data 20"]
    if extra_keywords:
        keywords += extra_keywords
    return any(k in line for k in keywords) or line.strip().isdigit()


def parse_table_rows(text, extra_furniture_keywords=None):
    """
    Parse raw extract_text() output into [{"label", "values", "n_values"}, ...],
    merging wrapped label lines onto the row that carries their numbers.
    """
    lines = text.split("\n")
    rows = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or is_furniture(line, extra_furniture_keywords):
            i += 1
            continue

        numbers = extract_numbers(line)
        if numbers:
            numbers = merge_split_decimals(numbers)
            first_num_start = re.search(r'-?\d[\d,]*\.?\d*', line).start()
            label = line[:first_num_start].strip()

            if i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                if nxt and not extract_numbers(nxt) and not is_furniture(nxt, extra_furniture_keywords):
                    label = f"{label} {nxt}"
                    i += 1

            rows.append({"label": label, "values": numbers, "n_values": len(numbers)})
        i += 1
    return rows


def rows_to_tidy_df(rows, years):
    """
    Convert parsed rows into a tidy (long-format) DataFrame: one row per
    (metric, year). Short rows are padded with None, never a guessed value.
    """
    records = []
    for r in rows:
        values = r["values"]
        if len(values) < len(years):
            values = values + [None] * (len(years) - len(values))
        for year, val in zip(years, values):
            clean_val = None if val is None else float(val.replace(",", ""))
            records.append({"metric": r["label"], "year": year, "value": clean_val})
    return pd.DataFrame(records)


def extract_table_as_df(pdf_path, page_index, years, extra_furniture_keywords=None):
    """Full pipeline for one page: open PDF, get text, parse rows, return tidy DataFrame."""
    with pdfplumber.open(pdf_path) as pdf:
        text = pdf.pages[page_index].extract_text()
    rows = parse_table_rows(text, extra_furniture_keywords)
    return rows_to_tidy_df(rows, years)