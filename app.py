from flask import Flask, render_template, request, redirect, url_for
import pyodbc
import os
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

connection_str = os.getenv("AZURE_SQL_CONNECTION")

def get_db_connection():
    conn = pyodbc.connect(connection_str)
    conn.autocommit = False  # Можно ставить True, но лучше контролировать вручную
    return conn

@app.route('/')
def index():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.EmployeeID, e.FirstName, e.LastName, d.DepartmentName, p.PositionName
        FROM Employees e
        LEFT JOIN Departments d ON e.DepartmentID = d.DepartmentID
        LEFT JOIN Positions p ON e.PositionID = p.PositionID
    """)
    employees = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("index.html", employees=employees)

@app.route('/employee/<int:employee_id>')
def view_employee(employee_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.*, d.DepartmentName, p.PositionName,
               a.Strasse, a.Hausnummer, a.PLZ, a.Stadt as AdresseStadt,
               o.Firma, o.Stadt as BüroStadt,
               c.Vertragsbeginn, c.Vertragsende, c.Gehalt
        FROM Employees e
        LEFT JOIN Departments d ON e.DepartmentID = d.DepartmentID
        LEFT JOIN Positions p ON e.PositionID = p.PositionID
        LEFT JOIN Addresses a ON e.AddressID = a.AddressID
        LEFT JOIN Offices o ON e.OfficeID = o.OfficeID
        LEFT JOIN Contracts c ON e.ContractID = c.ContractID
        WHERE e.EmployeeID = ?
    """, employee_id)
    employee = cursor.fetchone()
    cursor.close()
    conn.close()

    if employee is None:
        return "Mitarbeiter nicht gefunden", 404

    # Формируем адрес и офис в строку для удобства шаблона
    adresse = "–"
    if employee.Strasse or employee.Hausnummer or employee.PLZ or employee.AdresseStadt:
        adresse = f"{employee.Strasse or ''} {employee.Hausnummer or ''}, {employee.PLZ or ''} {employee.AdresseStadt or ''}".strip().strip(',')

    büro = "–"
    if employee.Firma or employee.BüroStadt:
        büro = f"{employee.Firma or ''} ({employee.BüroStadt or '–'})"

    vertragsbeginn = employee.Vertragsbeginn.strftime("%d.%m.%Y") if employee.Vertragsbeginn else '–'
    vertragsende = employee.Vertragsende.strftime("%d.%m.%Y") if employee.Vertragsende else 'laufend'
    gehalt = f"{employee.Gehalt} €" if employee.Gehalt else '–'

    return render_template("employee_detail.html",
                           employee=employee,
                           adresse=adresse,
                           büro=büro,
                           vertragsbeginn=vertragsbeginn,
                           vertragsende=vertragsende,
                           gehalt=gehalt)

@app.route('/employee/add', methods=['GET', 'POST'])
def add_employee():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT DepartmentID, DepartmentName FROM Departments")
    departments = cursor.fetchall()
    cursor.execute("SELECT PositionID, PositionName FROM Positions")
    positions = cursor.fetchall()

    if request.method == 'POST':
        data = request.form

        # Вставляем контракт и получаем ContractID
        cursor.execute("""
            INSERT INTO Contracts (Vertragsbeginn, Vertragsende, Gehalt)
            VALUES (?, ?, ?)
        """, (
            data.get('Vertragsbeginn') or None,
            data.get('Vertragsende') or None,
            data.get('Gehalt') or None,
        ))
        cursor.execute("SELECT SCOPE_IDENTITY()")
        contract_id = cursor.fetchone()[0]

        # Вставляем сотрудника с контрактом
        cursor.execute("""
            INSERT INTO Employees
            (FirstName, LastName, Telephone, Email, BirthDate, Benutzername, DepartmentID, PositionID, ContractID)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['FirstName'], data['LastName'], data['Telephone'], data['Email'],
            data['BirthDate'], data['Benutzername'], data['DepartmentID'], data['PositionID'], contract_id
        ))

        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('index'))

    cursor.close()
    conn.close()
    return render_template("form.html", employee=None, departments=departments, positions=positions)

@app.route('/employee/edit/<int:employee_id>', methods=['GET', 'POST'])
def edit_employee(employee_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT DepartmentID, DepartmentName FROM Departments")
    departments = cursor.fetchall()
    cursor.execute("SELECT PositionID, PositionName FROM Positions")
    positions = cursor.fetchall()

    if request.method == 'POST':
        data = request.form

        cursor.execute("""
            UPDATE Employees SET
                FirstName = ?, LastName = ?, Telephone = ?, Email = ?, BirthDate = ?, Benutzername = ?,
                DepartmentID = ?, PositionID = ?
            WHERE EmployeeID = ?
        """, (
            data['FirstName'], data['LastName'], data['Telephone'], data['Email'],
            data['BirthDate'], data['Benutzername'], data['DepartmentID'], data['PositionID'], employee_id
        ))

        cursor.execute("SELECT ContractID FROM Employees WHERE EmployeeID = ?", employee_id)
        contract_id = cursor.fetchone()[0]

        if contract_id:
            cursor.execute("""
                UPDATE Contracts SET
                    Vertragsbeginn = ?, Vertragsende = ?, Gehalt = ?
                WHERE ContractID = ?
            """, (
                data.get('Vertragsbeginn') or None,
                data.get('Vertragsende') or None,
                data.get('Gehalt') or None,
                contract_id
            ))
        else:
            cursor.execute("""
                INSERT INTO Contracts (Vertragsbeginn, Vertragsende, Gehalt)
                VALUES (?, ?, ?)
            """, (
                data.get('Vertragsbeginn') or None,
                data.get('Vertragsende') or None,
                data.get('Gehalt') or None,
            ))
            cursor.execute("SELECT SCOPE_IDENTITY()")
            new_contract_id = cursor.fetchone()[0]
            cursor.execute("UPDATE Employees SET ContractID = ? WHERE EmployeeID = ?", (new_contract_id, employee_id))

        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('index'))

    # GET - загрузка данных сотрудника
    cursor.execute("""
        SELECT e.*, d.DepartmentName, p.PositionName,
               c.Vertragsbeginn, c.Vertragsende, c.Gehalt
        FROM Employees e
        LEFT JOIN Departments d ON e.DepartmentID = d.DepartmentID
        LEFT JOIN Positions p ON e.PositionID = p.PositionID
        LEFT JOIN Contracts c ON e.ContractID = c.ContractID
        WHERE e.EmployeeID = ?
    """, employee_id)
    employee = cursor.fetchone()
    cursor.close()
    conn.close()

    if employee is None:
        return "Mitarbeiter nicht gefunden", 404

    return render_template("form.html", employee=employee, departments=departments, positions=positions)

@app.route('/employee/delete/<int:employee_id>', methods=['POST'])
def delete_employee(employee_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM Employees WHERE EmployeeID = ?", employee_id)
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
