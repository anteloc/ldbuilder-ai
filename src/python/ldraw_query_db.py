#!/usr/bin/env python

import sqlite3
import argparse
import os
import json
from typing import List, Dict, Any

def query_db(db_path: str, query: str) -> List[Dict[str, Any]]:
    """Query the SQLite database and return results as a list of dictionaries."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # This allows us to get results as dictionaries
    cursor = conn.cursor()
    
    cursor.execute(query)
    rows = cursor.fetchall()
    
    # Convert rows to list of dictionaries
    results = [dict(row) for row in rows]
    
    conn.close()
    return results

def main():
    parser = argparse.ArgumentParser(description="Query the LDraw database and return results as JSON.")
    parser.add_argument("db_path", help="Path to the SQLite database file.")
    parser.add_argument("query", help="SQL query to execute on the database.")
    
    args = parser.parse_args()
    
    results = query_db(args.db_path, args.query)
    
    # Print results as JSON
    for r in results:
        print(json.dumps(r))

if __name__ == "__main__":
    main()