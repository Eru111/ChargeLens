import os

import pandas as pd
from flask import Flask, request, render_template, redirect, url_for, send_file
from sqlalchemy import inspect, text
from io import BytesIO

from database import db, DB_USER, DB_PASS, DB_NAME, INSTANCE_CONNECTION_NAME
from data_importer import import_data_files
from db_query import get_table, create_indexes


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@/{DB_NAME}"
    f"?host=/cloudsql/{INSTANCE_CONNECTION_NAME}"
)
db.init_app(app)

@app.route("/")
def home():
    print(app.config["MAX_CONTENT_LENGTH"])
    return render_template("home.html")

@app.route("/upload-folder", methods=["GET", "POST"])
def upload_folder():
    if request.method == "POST":
        folder_path = request.form["folder_path"]

        import_data_files(folder_path)
        create_indexes()

        return redirect(url_for("view_tables"))
        '''    
        files = request.files.getlist("files")
        temp_dir = tempfile.mkdtemp()

        try:
            save_uploaded_folder(files, temp_dir)
            import_data_files(temp_dir)
            create_indexes()

            return redirect(url_for("view_tables"))

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        '''
    else:
        return render_template("upload_folder.html")

@app.route("/search", methods=["GET", "POST"])
def search():
    if request.method == "POST":
        search_type = request.form.get("search_type")

        user_input = request.form.get("user_input", "")
        user_input = [usr_input.strip().upper() for usr_input in user_input.split(",") if usr_input.strip()]

        months = request.form.getlist("months")

        services = request.form.get("services", "")
        services = [service.strip().upper() for service in services.split(",") if service.strip()]

        return redirect(url_for("result", search_type=search_type, user_input=user_input, months=months, services=services))
    else:
        return render_template("search.html")
        

        
@app.route("/view_tables")
def view_tables():
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()

    return render_template("tables.html", tables=tables)

@app.route("/delete-table/<table_name>", methods=["POST"])
def delete_table(table_name):
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()

    if table_name not in tables:
        return "Invalid table name", 400

    with db.engine.begin() as conn:
        conn.execute(text(f'''DROP TABLE "{table_name}"'''))

    return redirect(url_for("view_tables"))

@app.route("/result")
def result():
    search_type = request.args.get("search_type")

    user_input = request.args.getlist("user_input")
    user_input = [usr_input.strip().upper() for usr_input in user_input if usr_input.strip()]

    months = request.args.getlist("months")
    months = [month.strip() for month in months if month.strip()]

    services = request.args.getlist("services")
    services = [service.strip().upper() for service in services if service.strip()]

    table = get_table(search_type, user_input, months, services)

    return render_template(
        "result.html",
        table=table,
        search_type=search_type,
        user_input=user_input,
        months=months,
        services=services
    )

@app.route("/export")
def export_results():
    search_type = request.args.get("search_type")

    user_input = request.args.getlist("user_input")
    user_input = [usr_input.strip().upper() for usr_input in user_input if usr_input.strip()]

    months = request.args.getlist("months")
    months = [month.strip() for month in months if month.strip()]

    services = request.args.getlist("services")
    services = [service.strip().upper() for service in services if service.strip()]

    table = get_table(search_type, user_input, months, services)

    if not table:
        return "No data to export", 400

    df = pd.DataFrame(table)

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Results")

    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name=f"{user_input}_chargeback_results.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
    