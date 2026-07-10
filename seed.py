import sqlite3
import os
from app.database import init_db, get_db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'kayange.db')

from app.database import init_db, get_db


def seed():
    for f in os.listdir(BASE_DIR):
        if f.startswith('kayange.db'):
            os.remove(os.path.join(BASE_DIR, f))
    init_db()

    db = get_db()
    db.execute("PRAGMA foreign_keys = ON")

    db.execute('DELETE FROM audit_logs')
    db.execute('DELETE FROM departments')
    db.execute('DELETE FROM pharmacy_inventory')
    db.execute('DELETE FROM billing_items')
    db.execute('DELETE FROM billing')
    db.execute('DELETE FROM package_services')
    db.execute('DELETE FROM packages')

    departments = [
        ('General Medicine', 'General medical consultations and checkups'),
        ('Internal Medicine', 'Management of chronic diseases and complex internal conditions'),
        ('Pediatrics', 'Medical care for infants, children, and adolescents'),
        ('Maternity', 'Antenatal, delivery, and postnatal care'),
        ('Accident & Emergency', 'Emergency medical care for acute conditions and injuries'),
        ('Radiology', 'X-ray, ultrasound, and other imaging services'),
        ('Laboratory', 'Clinical lab tests and diagnostics'),
        ('Pharmacy', 'Dispensing of medications and pharmaceutical services'),
        ('Outpatient Services', 'Walk-in consultations and minor procedures'),
    ]
    for dept in departments:
        db.execute('INSERT INTO departments (name, description) VALUES (?,?)', dept)

    pharmacy_items = [
        ('Amoxicillin 500mg', 'Amoxicillin', 'Antibiotics', 500, 50.00, '2026-12-31', 'Mediplus Ltd', 50),
        ('Paracetamol 500mg', 'Paracetamol', 'Analgesics', 1000, 10.00, '2027-06-30', 'PharmaCo', 100),
        ('Ibuprofen 400mg', 'Ibuprofen', 'Analgesics', 300, 15.00, '2026-09-30', 'PharmaCo', 50),
        ('Metformin 850mg', 'Metformin', 'Diabetes', 400, 30.00, '2026-08-31', 'Mediplus Ltd', 30),
        ('Amlodipine 5mg', 'Amlodipine', 'Hypertension', 200, 25.00, '2026-11-30', 'HealthPharm', 25),
        ('Salbutamol Inhaler', 'Salbutamol', 'Respiratory', 50, 800.00, '2025-12-31', 'Mediplus Ltd', 10),
        ('Omeprazole 20mg', 'Omeprazole', 'GI', 250, 20.00, '2027-03-31', 'PharmaCo', 30),
        ('Cetirizine 10mg', 'Cetirizine', 'Antihistamines', 150, 8.00, '2027-01-31', 'HealthPharm', 40),
        ('Diclofenac Gel', 'Diclofenac', 'Topical', 80, 350.00, '2026-10-31', 'Mediplus Ltd', 15),
        ('Multivitamin Tablets', 'Multivitamin', 'Supplements', 600, 5.00, '2027-12-31', 'HealthPharm', 100),
        ('Red Top Tube (Serum)', 'Vacutainer Red', 'Lab Supplies', 500, 12.00, '2028-06-30', 'BD Medical', 100),
        ('Purple Top Tube (EDTA)', 'Vacutainer EDTA', 'Lab Supplies', 500, 14.00, '2028-06-30', 'BD Medical', 100),
    ]

    for item in pharmacy_items:
        db.execute(
            'INSERT INTO pharmacy_inventory (drug_name, generic_name, category, stock_quantity, unit_price, expiry_date, supplier, reorder_level) VALUES (?,?,?,?,?,?,?,?)',
            item)

    packages = [
        ('Annual Health Checkup', 'Comprehensive annual health screening', 5000.00),
        ('Maternity Package', 'Antenatal and postnatal care', 15000.00),
        ('Diabetes Care Plan', 'Monthly diabetes management', 3000.00),
        ('Executive Wellness', 'Executive health and wellness package', 25000.00),
    ]

    for pkg in packages:
        db.execute('INSERT INTO packages (package_name, description, total_amount) VALUES (?,?,?)', pkg)

    package_services = [
        (1, 'Full blood count', 'lab'), (1, 'Blood sugar test', 'lab'), (1, 'Urinalysis', 'lab'),
        (1, 'ECG', 'procedure'), (1, 'General consultation', 'consultation'),
        (2, 'Antenatal consultation', 'consultation'), (2, 'Ultrasound scan', 'lab'), (2, 'Blood tests', 'lab'),
        (3, 'HbA1c test', 'lab'), (3, 'Dietary consultation', 'consultation'), (3, 'Monthly checkup', 'consultation'),
        (4, 'Full blood count', 'lab'), (4, 'Lipid profile', 'lab'), (4, 'ECG', 'procedure'),
        (4, 'Stress test', 'procedure'), (4, 'Nutrition plan', 'consultation'),
    ]

    for ps in package_services:
        db.execute('INSERT INTO package_services (package_id, service_name, service_type) VALUES (?,?,?)', ps)

    db.commit()
    db.close()
    print('Database seeded successfully!')


if __name__ == '__main__':
    seed()
