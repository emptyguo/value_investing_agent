#!/usr/bin/env python3
import json
import argparse
import sys
import os

COMPANY_DICT_PATH = os.environ.get(
    "OPENCLAW_COMPANY_DICT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../workspace_data/references/companies.json")),
)

def load_company_dict():
    if not os.path.exists(COMPANY_DICT_PATH):
        print(f"Error: {COMPANY_DICT_PATH} not found.")
        sys.exit(1)
    with open(COMPANY_DICT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_company_dict(data):
    # Write directly with indent
    with open(COMPANY_DICT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def main():
    parser = argparse.ArgumentParser(description="Dynamically update companies.json monitoring radar.")
    parser.add_argument("action", choices=["add", "remove"], help="Action to perform")
    parser.add_argument("company_id", help="Company ID, e.g., tencent")
    parser.add_argument("field", choices=["brands", "competitors", "industry_keywords", "aliases"], help="Field to update")
    parser.add_argument("value", help="The keyword value to add or remove")

    args = parser.parse_args()

    data = load_company_dict()
    companies = data.get("companies", [])

    target = None
    for c in companies:
        if c.get("id") == args.company_id:
            target = c
            break
            
    if not target:
        print(f"Error: Company '{args.company_id}' not found.")
        sys.exit(1)

    field_list = target.get(args.field, [])

    if args.action == "add":
        if args.value not in field_list:
            field_list.append(args.value)
            print(f"Success: Added '{args.value}' to {args.company_id}.{args.field}.")
        else:
            print(f"Info: Value '{args.value}' already exists in {args.company_id}.{args.field}.")
    elif args.action == "remove":
        if args.value in field_list:
            field_list.remove(args.value)
            print(f"Success: Removed '{args.value}' from {args.company_id}.{args.field}.")
        else:
            print(f"Info: Value '{args.value}' not found in {args.company_id}.{args.field}.")
            
    target[args.field] = field_list
    save_company_dict(data)

if __name__ == "__main__":
    main()
