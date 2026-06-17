from sqlalchemy import inspect, text

from database import db


MONTHS = {"1": "January",
          "2": "February",
          "3": "March",
          "4": "April",
          "5": "May",
          "6": "June",
          "7": "July",
          "8": "August",
          "9": "September",
          "10": "October",
          "11": "November",
          "12": "December",
}

def validate_table(table_name):
    inspector = inspect(db.engine)

    tables = inspector.get_table_names()
    if table_name not in tables:
        raise ValueError("Invalid table name")

def get_table(search_type, user_input, months, services):
    rows = get_filtered_rows(search_type, user_input, months, services)

    final_table = remove_backend_columns(rows)
    total_price = sum_price(final_table)

    if final_table:
        total_row = {key: "" for key in final_table[0].keys()}
        total_row["Additional Info"] = "Total Price:"
        total_row["Price"] = total_price
        final_table.append(total_row)

    return final_table

def get_filtered_rows(search_type, user_input, months, services):
    query = '''
        SELECT *
        FROM costing_data
        WHERE 1 = 1
    '''
    params = {}

    if user_input and search_type:
        ccc_list = find_ccc(search_type, user_input)

        rows = db.session.execute(text(''' SELECT DISTINCT "Receiver CC" FROM costing_data LIMIT 10''')).mappings().all()

        if not ccc_list:
            return []

        query, params = add_in_filter(query, params, "Receiver CC", "ccc", ccc_list)

    query, params = add_month_filter(query, params, months)

    query, params = add_in_filter(query, params, "Activity", "service", services)

    rows = db.session.execute(
        text(query),
        params
    ).mappings().all()

    return rows

def remove_backend_columns(rows):
    clean_table = []

    for row in rows:
        row_dict = dict(row)

        row_dict.pop("Source_file", None)
        row_dict.pop("Source_folder", None)

        clean_table.append(row_dict)

    return clean_table

def sum_price(table):
    total = 0

    for row in table:
        price = row["Price"]

        if price is None:
            continue

        try:
            total += float(price)
        except ValueError:
            continue

    return round(total, 2)

def find_ccc(search_type, user_input):
    table_name = "chargeback_ccc"
    validate_table(table_name)

    if search_type == "cc":
        search_column = "Cost Center"
    elif search_type == "org":
        search_column = "SAP Org code"
    else:
        return []

    query = '''
        SELECT "CCC"
        FROM "chargeback_ccc"
        WHERE 1 = 1
    '''

    params = {}
    query, params = add_in_filter(query, params, search_column, "input", user_input)

    rows = db.session.execute(text(query), params).mappings().all()

    return [row["CCC"] for row in rows if row["CCC"] is not None]

def add_in_filter(query, params, column_name, param_prefix, values):
    if not values:
        return query, params

    placeholders = []

    for i, value in enumerate(values):
        key = f"{param_prefix}_{i}"
        placeholders.append(f":{key}")
        params[key] = value

    query += f'''
        AND "{column_name}" IN ({",".join(placeholders)})
    '''

    return query, params

def add_month_filter(query, params, months):
    if not months:
        return query, params
    
    month_names = [MONTHS[m] for m in months]

    if not month_names:
        return query, params

    return add_in_filter(query, params, "Month", "month", month_names)

def create_indexes():
    inspector = inspect(db.engine)
    if "costing_data" in inspector.get_table_names():
        db.session.execute(text(
            'CREATE INDEX IF NOT EXISTS idx_ccc ON costing_data ("Receiver CC")'
        ))

        db.session.execute(text(
            'CREATE INDEX IF NOT EXISTS idx_service ON costing_data ("Activity")'
        ))

        db.session.execute(text(
            'CREATE INDEX IF NOT EXISTS idx_month ON costing_data ("Month")'
        ))

        db.session.commit()

def load_service_prices():
    query = text('''
        SELECT "Activity Type", "Price (Fixed)"
        FROM it_activity_types_2026_rates
    ''')
    rows = db.session.execute(query).mappings().all()
    return {row["Activity Type"]: row["Price (Fixed)"] for row in rows}

def load_service_description():
    query = text('''
        SELECT "Service Code", "Service Description"
        FROM service_description
    ''')
    rows = db.session.execute(query).mappings().all()
    return {row["Service Code"]: row["Service Description"] for row in rows}

def get_monthly_totals():
    rows = db.session.execute(text('''
        SELECT "Month",
               SUM("Price") AS total_cost
        FROM costing_data
        GROUP BY "Month"
    ''')).mappings().all()

    return rows
