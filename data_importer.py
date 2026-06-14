import os
import re

import pandas as pd
from sqlalchemy import inspect, text
from werkzeug.utils import secure_filename

from database import db
from db_query import load_service_description, load_service_prices


COSTING_TABLE = "costing_data"
CHARGEBACK_CONFIG_FILE = "chargeback_configuration"
CHARGEBACK_CCC_SHEET = "CCC"
CHARGEBACK_CCC_TABLE = "chargeback_ccc"
CHARGEBACK_EQUIVALENCE_SHEET = "Equivalence"
CHARGEBACK_EQUIVALENCE_TABLE = "chargeback_exclusions"
SERVICE_RATE_TABLE = "it_activity_types_2026_rates"
RECEIVER_CC_COLUMN = "Receiver CC"
ACTIVITY_COLUMN = "Activity"
SERVICE_DESCRIPTION_TABLE = "service_description"

def make_table_name(filename):
    name = os.path.splitext(filename)[0]
    name = re.sub(r"[^a-zA-Z0-9-_]+", "_", name).strip("_").lower()

    if name and name[0].isdigit():
        name = "_" + name

    return name

def read_data_file(file_path):
    if file_path.lower().endswith(".csv"):
        return pd.read_csv(file_path)
    if file_path.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(file_path)

    return None

def read_costing_data_file(file_path):
    if file_path.lower().endswith(".csv"):
        return pd.read_csv(file_path, usecols=range(8))
    if file_path.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(file_path, usecols=range(8))

    return None

def save_uploaded_folder(files, temp_dir):
    for file in files:
        if not file.filename.endswith((".csv", ".xlsx", ".xls")):
            continue
        
        relative_path = file.filename
        safe_parts = [secure_filename(part) for part in relative_path.split("/")]

        save_path = os.path.join(temp_dir, *safe_parts)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        file.save(save_path)

def get_path_parts(root):
    return [part.lower() for part in os.path.normpath(root).split(os.sep)]

def get_month_from_path(root):
    parts = get_path_parts(root)

    for part in parts:
        if "-" in part and part.split("-", 1)[0].isdigit():
            return part.split("-", 1)[1].capitalize()

    return None

def should_skip_folder(root):
    parts = get_path_parts(root)
    return "raw" in parts

def should_skip_file(filename):
    return filename.startswith("~$")

def is_upload_folder(root):
    parts = get_path_parts(root)
    return "upload" in parts

def is_chargeback_config_file(filename):
    return make_table_name(filename) == CHARGEBACK_CONFIG_FILE

def is_service_rate_file(filename):
    return make_table_name(filename) == SERVICE_RATE_TABLE

def is_service_description_file(filename):
    return make_table_name(filename) == SERVICE_DESCRIPTION_TABLE

def clean_columns(df):
    df.columns = df.columns.str.strip()
    return df

def clean_data_columns(df):
    new_columns = []

    for column in df.columns.str.strip():
        cc = column.find("CC")
        order = column.find("Order")
        wbs = column.find("WBS")
        idn = column.find("ID")
        info = column.find("Info")
        is_qty = "qty" == column.lower()

        if cc != -1 and column[cc-1] != " ":
            column = column[:cc] + " " + column[cc:]
        if order != -1 and column[order-1] != " ":
            column = column[:order] + " " + column[order:]
        if wbs != -1 and column[wbs-1] != " ":
            column = column[:wbs] + " " + column[wbs:]
        if idn != -1 and column[idn-1] != " ":
            column = column[:idn] + " " + column[idn:]
        if info != -1 and column[info-1] != " ":
            column = column[:info] + " " + column[info:]
        if is_qty:
            column = "Qty"

        new_columns.append(column)

    df.columns = new_columns
    return df

def add_metadata_columns(df, file, root, month, price_map, description_map):
    df["Source_file"] = file
    df["Source_folder"] = os.path.basename(root)
    df["Price"] = df["Activity"].map(price_map)
    df["Month"] = month
    df["Description"] = df["Activity"].map(description_map)
    return df

def import_chargeback_config(file_path):
    ccc_df = pd.read_excel(file_path, sheet_name=CHARGEBACK_CCC_SHEET)
    ccc_df = clean_columns(ccc_df)

    ccc_df.to_sql(
        name=CHARGEBACK_CCC_TABLE,
        con=db.engine,
        if_exists="replace",
        index=False
    )

    equivalence_df = pd.read_excel(file_path, sheet_name=CHARGEBACK_EQUIVALENCE_SHEET)
    equivalence_df = clean_columns(equivalence_df)

    equivalence_df = equivalence_df[
        equivalence_df["Need To Be Charged"]
        .astype(str)
        .str.strip()
        .str.lower()
        == "no"
    ]

    equivalence_df.to_sql(
        name=CHARGEBACK_EQUIVALENCE_TABLE,
        con=db.engine,
        if_exists="replace",
        index=False
    )

def exclusions_exist():
    inspector = inspect(db.engine)
    return CHARGEBACK_EQUIVALENCE_TABLE in inspector.get_table_names()

def load_exclusions():
    rows = db.session.execute(text(f'''
        SELECT "Code"
        FROM {CHARGEBACK_EQUIVALENCE_TABLE}
    ''')).mappings().all()
    
    exclusions = [row["Code"] for row in rows if row["Code"] is not None]
    return exclusions

def import_data_files(base_folder):
    for root, dirs, files in os.walk(base_folder):
        for file in files:
            if should_skip_file(file):
                continue 

            file_path = os.path.join(root, file)

            if is_chargeback_config_file(file):
                import_chargeback_config(file_path)
                continue

            df = read_data_file(file_path)

            if df is None:
                continue

            df = clean_columns(df)

            if is_service_rate_file(file):
                df.to_sql(
                    name=SERVICE_RATE_TABLE,
                    con=db.engine,
                    if_exists="replace",
                    index=False
                )
                continue

            if is_service_description_file(file):
                df.to_sql(
                    name=SERVICE_DESCRIPTION_TABLE,
                    con=db.engine,
                    if_exists="replace",
                    index=False
                )
                continue

    price_map = load_service_prices()
    description_map = load_service_description()

    all_dfs = []

    for root, dirs, files in os.walk(base_folder):
        if should_skip_folder(root):
            continue
        if not is_upload_folder(root):
            continue

        month = get_month_from_path(root)

        for file in files:

            print(root, dirs, files)
            if is_chargeback_config_file(file) or is_service_rate_file(file) or is_service_description_file(file):
                continue

            file_path = os.path.join(root, file)
            df = read_costing_data_file(file_path)

            if df is None:
                continue

            df = clean_data_columns(df)

            df = add_metadata_columns(df, file, root, month, price_map, description_map)
            all_dfs.append(df)

    if all_dfs:
        final_df = pd.concat(all_dfs, ignore_index=True)

        if exclusions_exist():
            exclusions = load_exclusions()
            final_df = final_df[
                ~final_df["Activity"].isin(exclusions)
            ]

        uploaded_months = final_df["Month"].unique().tolist()

        inspector = inspect(db.engine)
        table_exists = COSTING_TABLE in inspector.get_table_names()

        with db.engine.begin() as conn:
            if table_exists:
                for month in uploaded_months:
                    conn.execute(text(f'''DELETE FROM "{COSTING_TABLE}" WHERE "Month" = :month'''), {"month": month})

            final_df.to_sql(
                name=COSTING_TABLE,
                con=conn,
                if_exists="append",
                index=False
            )
