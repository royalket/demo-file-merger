from flask import Flask, request, send_file, render_template_string, jsonify
import pandas as pd
import json
import io
import numpy as np
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

def format_date(date_str, format_type):
    if pd.isna(date_str) or date_str == '':
        return ''
    try:
        if isinstance(date_str, str):
            for fmt in ['%m/%d/%Y', '%m-%d-%Y', '%Y-%m-%d', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S']:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue
            else:
                dt = pd.to_datetime(date_str, errors='coerce')
                if pd.isna(dt):
                    print(f"Date parsing failed for: {date_str}")
                    return str(date_str)
        else:
            dt = pd.to_datetime(date_str, errors='coerce')
            if pd.isna(dt):
                print(f"Date parsing failed for non-string: {date_str}")
                return str(date_str)
        if format_type == 'YYYY-MM-DD':
            return dt.strftime('%Y-%m-%d')
        elif format_type == 'MM/DD/YYYY':
            return dt.strftime('%m/%d/%Y')
        elif format_type == 'DD/MM/YYYY':
            return dt.strftime('%d/%m/%Y')
        else:
            return dt.strftime('%Y-%m-%d')
    except Exception as e:
        print(f"Date formatting error: {e}, input: {date_str}")
        return str(date_str)

def calculate_age(dob_str, service_date_str):
    if not dob_str or not service_date_str or pd.isna(dob_str) or pd.isna(service_date_str):
        print(f"Missing DOB or service date: DOB={dob_str}, Service Date={service_date_str}")
        return ''
    try:
        dob_formats = ['%m/%d/%Y', '%m-%d-%Y', '%Y-%m-%d', '%d/%m/%Y']
        service_formats = ['%m/%d/%Y', '%m-%d-%Y', '%Y-%m-%d', '%d/%m/%Y']
        
        dob = None
        for fmt in dob_formats:
            try:
                dob = datetime.strptime(str(dob_str), fmt)
                print(f"Parsed DOB: {dob_str} as {dob} with format {fmt}")
                break
            except ValueError:
                continue
        if not dob:
            dob = pd.to_datetime(dob_str, errors='coerce')
            if pd.isna(dob):
                print(f"Failed to parse DOB: {dob_str}")
                return ''

        service_date = None
        for fmt in service_formats:
            try:
                service_date = datetime.strptime(str(service_date_str), fmt)
                print(f"Parsed Service Date: {service_date_str} as {service_date} with format {fmt}")
                break
            except ValueError:
                continue
        if not service_date:
            service_date = pd.to_datetime(service_date_str, errors='coerce')
            if pd.isna(service_date):
                print(f"Failed to parse Service Date: {service_date_str}")
                return ''

        age = (service_date - dob).days // 365
        if age >= 0:
            print(f"Calculated age: {age} for DOB={dob_str}, Service Date={service_date_str}")
            return str(age)
        else:
            print(f"Negative age calculated: {age} for DOB={dob_str}, Service Date={service_date_str}")
            return ''
    except Exception as e:
        print(f"Age calculation error: {e}, DOB={dob_str}, Service Date={service_date_str}")
        return ''

def load_reference_data(files_data):
    procedures_df = pd.DataFrame()
    providers_df = pd.DataFrame()
    facilities_df = pd.DataFrame()
    
    for filename, file_content in files_data.items():
        try:
            if 'procedures' in filename.lower() and filename.endswith('.json'):
                procedures_data = json.loads(file_content.decode('utf-8'))
                procedures_df = pd.DataFrame(procedures_data)
            elif 'providers' in filename.lower() and filename.endswith('.json'):
                providers_data = json.loads(file_content.decode('utf-8'))
                providers_df = pd.DataFrame(providers_data)
            elif 'facilities' in filename.lower() and filename.endswith('.json'):
                facilities_data = json.loads(file_content.decode('utf-8'))
                facilities_list = []
                for fid, finfo in facilities_data.items():
                    fac = {"id": fid}
                    fac.update(finfo)
                    if "address" in finfo:
                        fac.update(finfo["address"])
                    facilities_list.append(fac)
                facilities_df = pd.DataFrame(facilities_list)
        except Exception as e:
            print(f"Error loading reference file {filename}: {e}")
    
    return procedures_df, providers_df, facilities_df

def process_medical_claims(files_data, date_format='YYYY-MM-DD'):
    records_df = None
    patients_df = None
    procedures_df, providers_df, facilities_df = load_reference_data(files_data)

    for filename, file_content in files_data.items():
        try:
            if 'records' in filename.lower() and (filename.endswith('.xlsx') or filename.endswith('.csv')):
                if filename.endswith('.xlsx'):
                    excel_file = pd.ExcelFile(io.BytesIO(file_content))
                    for sheet_name in excel_file.sheet_names:
                        sheet_df = pd.read_excel(io.BytesIO(file_content), sheet_name=sheet_name)
                        if any(col.lower() in ['claim_id', 'cpt_code', 'charge_amount', 'rendering_npi'] for col in sheet_df.columns):
                            records_df = sheet_df
                        elif any(col.lower() in ['patient_id', 'first_name', 'last_name', 'dob'] for col in sheet_df.columns):
                            patients_df = sheet_df
                else:
                    records_df = pd.read_csv(io.BytesIO(file_content))
        except Exception as e:
            print(f"Error processing file {filename}: {e}")
            continue

    if records_df is None:
        raise ValueError("Records Excel/CSV file is required")

    records_df.columns = records_df.columns.str.strip()
    if patients_df is not None:
        patients_df.columns = patients_df.columns.str.strip()

    claim_id_col = next((col for col in records_df.columns if 'claim' in col.lower() and 'id' in col.lower()), None)
    if not claim_id_col:
        raise ValueError("Could not find claim_id column in records data")

    consolidated_claims = []
    for claim_id, group in records_df.groupby(claim_id_col):
        try:
            first_row = group.iloc[0]
            charge_col = next((col for col in records_df.columns if 'charge' in col.lower() and 'amount' in col.lower()), None)
            total_charge = 0
            if charge_col:
                charges = pd.to_numeric(group[charge_col].astype(str).str.replace('[\$,]', '', regex=True), errors='coerce').fillna(0)
                total_charge = charges.sum()

            patient_id = next((first_row[col] for col in records_df.columns if 'patient' in col.lower() and 'id' in col.lower() and pd.notna(first_row[col])), None)
            patient_name = ''
            dob = ''
            gender = ''
            if patients_df is not None and patient_id is not None:
                patient_id_col = next((col for col in patients_df.columns if 'patient' in col.lower() and 'id' in col.lower()), None)
                if patient_id_col:
                    patient_row = patients_df[patients_df[patient_id_col] == patient_id]
                    if not patient_row.empty:
                        patient_info = patient_row.iloc[0]
                        first_name = patient_info.get('first_name', '') or ''
                        last_name = patient_info.get('last_name', '') or ''
                        patient_name = f"{first_name} {last_name}".strip()
                        dob = patient_info.get('dob', '') or ''
                        gender = patient_info.get('gender', '') or ''
                        print(f"Patient found: ID={patient_id}, Name={patient_name}, DOB={dob}, Gender={gender}")

            service_date_col = next((col for col in records_df.columns if 'date' in col.lower() and 'service' in col.lower()), None)
            start_service_date = ''
            if service_date_col:
                dates = group[service_date_col].dropna()
                if not dates.empty:
                    start_service_date = dates.min()
                    print(f"Service date for claim {claim_id}: {start_service_date}")

            age = calculate_age(dob, start_service_date) if dob and start_service_date else ''
            print(f"Age for claim {claim_id}: {age}")

            procedure_code_col = next((col for col in records_df.columns if 'cpt' in col.lower() and 'code' in col.lower()), None)
            procedure_descriptions = []
            if procedure_code_col and not procedures_df.empty:
                procedure_codes = group[procedure_code_col].dropna().astype(str).str.strip().unique()
                for proc_code in procedure_codes:
                    proc_info = procedures_df[procedures_df['code'] == proc_code]
                    if not proc_info.empty:
                        desc = proc_info.iloc[0]['description']
                        if pd.notna(desc):
                            procedure_descriptions.append(str(desc))

            provider_npi_col = next((col for col in records_df.columns if 'npi' in col.lower()), None)
            provider_name = ''
            provider_specialty = ''
            facility_id = ''
            if provider_npi_col and not providers_df.empty:
                provider_npi = first_row[provider_npi_col]
                if pd.notna(provider_npi):
                    provider_npi_str = str(provider_npi).strip()
                    provider_info = providers_df[providers_df['npi'] == provider_npi_str]
                    if not provider_info.empty:
                        provider_name = str(provider_info.iloc[0]['name'])
                        provider_specialty = str(provider_info.iloc[0]['specialty'])
                        facility_id = provider_info.iloc[0].get('facility_id', '')

            facility_state = ''
            facility_name = ''
            if facility_id and not facilities_df.empty:
                facility_info = facilities_df[facilities_df['id'] == facility_id]
                if not facility_info.empty:
                    facility_state = str(facility_info.iloc[0].get('state', ''))
                    facility_name = str(facility_info.iloc[0].get('name', ''))

            consolidated_claim = {
                'Claim ID': str(claim_id),
                'Patient Name': patient_name,
                'Date of Birth': format_date(dob, date_format),
                'Gender': gender,
                'Age': age,
                'Total Charge Amount': f"${total_charge:.2f}",
                'Starting Service Date': format_date(start_service_date, date_format),
                'Procedure Descriptions': ', '.join(procedure_descriptions) if procedure_descriptions else '',
                'Rendering Provider Name': provider_name,
                'Provider Specialty': provider_specialty,
                'Facility State': facility_state,
                'Facility Name': facility_name
            }
            consolidated_claims.append(consolidated_claim)
            print(f"Processed claim {claim_id} with Age: {age}")
        except Exception as e:
            print(f"Error processing claim {claim_id}: {e}")
            continue

    result_df = pd.DataFrame(consolidated_claims)
    print("Columns in output DataFrame:", result_df.columns.tolist())
    return result_df

def calculate_claim_analytics(records_df):
    analytics = {
        'total_claims': len(records_df),
        'total_patients': len(records_df['Patient Name'].unique()) if 'Patient Name' in records_df.columns else 0,
        'total_amount': "$0.00",
        'date_range': "No dates available",
        'claims_by_specialty': {},
        'top_procedures': [],
        'claims_by_gender': {},
        'claims_by_state': {}
    }
    
    if 'Total Charge Amount' in records_df.columns:
        charge = pd.to_numeric(records_df['Total Charge Amount'].str.replace('[\$,]', '', regex=True), errors='coerce').fillna(0)
        analytics['total_amount'] = f"${charge.sum():.2f}"
    
    if 'Starting Service Date' in records_df.columns:
        valid_dates = records_df['Starting Service Date'].dropna()
        if not valid_dates.empty:
            analytics['date_range'] = f"{valid_dates.min()} to {valid_dates.max()}"
    
    if 'Provider Specialty' in records_df.columns:
        specialty_counts = records_df['Provider Specialty'].value_counts().to_dict()
        analytics['claims_by_specialty'] = {k: int(v) for k, v in specialty_counts.items()}
    
    if 'Procedure Descriptions' in records_df.columns:
        procedures = records_df['Procedure Descriptions'].str.split(', ').explode()
        top_procs = procedures.value_counts().head(5).to_dict()
        analytics['top_procedures'] = [{'procedure': k, 'count': int(v)} for k, v in top_procs.items() if k]
    
    if 'Gender' in records_df.columns:
        gender_counts = records_df['Gender'].value_counts().to_dict()
        analytics['claims_by_gender'] = {k: int(v) for k, v in gender_counts.items() if k}
    
    if 'Facility State' in records_df.columns:
        state_counts = records_df['Facility State'].value_counts().to_dict()
        analytics['claims_by_state'] = {k: int(v) for k, v in state_counts.items() if k}
    
    return analytics

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Medical Claims Processor</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/materialize/1.0.0/css/materialize.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: 'Poppins', sans-serif; }
        .gradient-bg { background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%); }
        .file-item { transition: all 0.3s ease; backdrop-filter: blur(10px); }
        .file-item:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(0,0,0,0.2); }
        .upload-zone { border: 2px dashed #d1d5db; transition: all 0.3s ease; }
        .upload-zone.drag-over { border-color: #4f46e5; background-color: rgba(79, 70, 229, 0.1); }
        .glass-card { background: rgba(255, 255, 255, 0.15); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.3); }
        .table-container { max-height: 400px; overflow-y: auto; }
        .spinner { border: 4px solid rgba(255, 255, 255, 0.3); border-top: 4px solid #4f46e5; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: auto; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .fade-in { opacity: 0; animation: fadeIn 0.5s ease-in forwards; }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        .chart-container { max-width: 100%; height: 200px; }
        .summary-table th, .summary-table td { border: 1px solid rgba(255, 255, 255, 0.2); padding: 8px; }
        .file-input { background: rgba(255, 255, 255, 0.1); border: 1px solid rgba(255, 255, 255, 0.3); color: white; padding: 8px; border-radius: 8px; }
    </style>
</head>
<body class="min-h-screen gradient-bg">
    <nav class="transparent z-depth-0">
        <div class="nav-wrapper container">
            <a href="#" class="brand-logo white-text"><i class="material-icons left">local_hospital</i>Medical Claims Processor</a>
        </div>
    </nav>
    <div class="container mx-auto px-4 py-12">
        <div class="glass-card rounded-2xl p-8 mb-8 shadow-lg">
            <h2 class="text-3xl font-bold text-white mb-2 text-center"><i class="material-icons text-4xl align-middle mr-2">cloud_upload</i>File Processing Center</h2>
            <p class="text-white text-opacity-80 text-center mb-8 text-lg">Upload medical records, procedures, providers, and facilities files for detailed analytics</p>
            <div class="mb-8">
                <div class="upload-zone rounded-xl p-8 text-center bg-white bg-opacity-10" id="uploadZone" ondrop="dropHandler(event);" ondragover="dragOverHandler(event);" ondragleave="dragLeaveHandler(event);">
                    <i class="material-icons text-6xl text-white mb-4">cloud_upload</i>
                    <h3 class="text-xl font-semibold text-white mb-2">Drop files here or select below</h3>
                    <p class="text-white text-opacity-70 mb-4">Supports Excel (.xlsx), JSON, and CSV files</p>
                    <input type="file" id="fileInput" multiple accept=".xlsx,.json,.csv" class="file-input w-full mb-4" onchange="handleFileSelect(event)">
                    <button class="btn-large waves-effect waves-light bg-indigo-600 hover:bg-indigo-700" onclick="triggerFileInput()">
                        <i class="material-icons left">attach_file</i>Choose Files
                    </button>
                </div>
            </div>
            <div class="mb-8">
                <h4 class="text-xl font-semibold text-white mb-4"><i class="material-icons align-middle mr-2">folder_open</i>Uploaded Files</h4>
                <div id="filesList" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"></div>
                <div id="emptyState" class="text-center py-8">
                    <i class="material-icons text-5xl text-white text-opacity-50">inbox</i>
                    <p class="text-white text-opacity-70 mt-2">No files uploaded yet</p>
                </div>
            </div>
            <div class="bg-white bg-opacity-10 rounded-xl p-6">
                <h4 class="text-xl font-semibold text-white mb-4"><i class="material-icons align-middle mr-2">settings</i>Processing Options</h4>
                <div class="row mb-4">
                    <div class="col s12 m6 l3">
                        <label class="text-white">Output Format</label>
                        <select id="outputFormat" class="browser-default white-text bg-black bg-opacity-20 rounded p-2 mt-2">
                            <option value="csv" selected>CSV</option>
                            <option value="excel">Excel (.xlsx)</option>
                            <option value="json">JSON</option>
                        </select>
                    </div>
                    <div class="col s12 m6 l3">
                        <label class="text-white">Date Format</label>
                        <select id="dateFormat" class="browser-default white-text bg-black bg-opacity-20 rounded p-2 mt-2">
                            <option value="YYYY-MM-DD" selected>YYYY-MM-DD</option>
                            <option value="MM/DD/YYYY">MM/DD/YYYY</option>
                            <option value="DD/MM/YYYY">DD/MM/YYYY</option>
                        </select>
                    </div>
                </div>
                <div class="text-center space-x-4">
                    <button id="processBtn" class="btn-large waves-effect waves-light bg-green-600 hover:bg-green-700 disabled:opacity-50" onclick="processFiles()" disabled>
                        <i class="material-icons left">play_arrow</i>Process Files
                    </button>
                    <button id="previewBtn" class="btn-large waves-effect waves-light bg-orange-600 hover:bg-orange-700 disabled:opacity-50" onclick="previewData()" disabled>
                        <i class="material-icons left">visibility</i>Preview Data
                    </button>
                </div>
            </div>
        </div>
        <div id="previewSection" class="glass-card rounded-2xl p-8 mb-8 hidden">
            <h4 class="text-2xl font-semibold text-white mb-6"><i class="material-icons align-middle mr-2">preview</i>Data Preview</h4>
            <div id="previewContent" class="bg-white bg-opacity-10 rounded-xl p-6">
                <div id="loadingSpinner" class="spinner"></div>
                <div id="previewData" class="hidden fade-in">
                    <div class="mb-6">
                        <h5 class="text-xl font-semibold text-white mb-4">Analytics Summary</h5>
                        <table class="summary-table w-full text-white bg-white bg-opacity-10 rounded-lg">
                            <thead>
                                <tr>
                                    <th>Total Claims</th>
                                    <th>Total Patients</th>
                                    <th>Total Amount</th>
                                    <th>Date Range</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td id="totalClaims"></td>
                                    <td id="totalPatients"></td>
                                    <td id="totalAmount"></td>
                                    <td id="dateRange"></td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                        <div class="chart-container">
                            <canvas id="specialtyChart"></canvas>
                        </div>
                        <div class="chart-container">
                            <canvas id="procedureChart"></canvas>
                        </div>
                        <div class="chart-container">
                            <canvas id="genderChart"></canvas>
                        </div>
                        <div class="chart-container">
                            <canvas id="stateChart"></canvas>
                        </div>
                    </div>
                    <h5 class="text-xl font-semibold text-white mb-4">Sample Claims</h5>
                    <div class="table-container">
                        <table class="highlight responsive-table text-white">
                            <thead><tr id="tableHeaders"></tr></thead>
                            <tbody id="tableBody"></tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
        <div id="progressSection" class="glass-card rounded-2xl p-6 mb-8 hidden">
            <h4 class="text-xl font-semibold text-white mb-4"><i class="material-icons align-middle mr-2">hourglass_empty</i>Processing...</h4>
            <div class="progress bg-white bg-opacity-20"><div id="progressBar" class="determinate bg-indigo-600" style="width: 0%"></div></div>
            <p id="progressText" class="text-white text-center mt-2">Preparing files...</p>
        </div>
    </div>
    <div id="toast-container"></div>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/materialize/1.0.0/js/materialize.min.js"></script>
    <script>
        let uploadedFiles = [];
        let charts = {
            specialty: null,
            procedure: null,
            gender: null,
            state: null
        };
        let isPreviewLoading = false;

        function getFileType(filename) {
            const extension = filename.split('.').pop().toLowerCase();
            const typeMap = {
                'xlsx': { type: 'Excel', color: 'green', icon: 'table_chart' },
                'json': { type: 'JSON', color: 'orange', icon: 'code' },
                'csv': { type: 'CSV', color: 'blue', icon: 'description' }
            };
            return typeMap[extension] || { type: 'Unknown', color: 'grey', icon: 'help' };
        }
        function dragOverHandler(ev) {
            ev.preventDefault();
            document.getElementById('uploadZone').classList.add('drag-over');
            console.log('Drag over upload zone');
        }
        function dragLeaveHandler(ev) {
            document.getElementById('uploadZone').classList.remove('drag-over');
            console.log('Drag left upload zone');
        }
        function dropHandler(ev) {
            ev.preventDefault();
            document.getElementById('uploadZone').classList.remove('drag-over');
            const files = ev.dataTransfer.files;
            console.log('Dropped files:', files.length);
            handleFiles(files);
        }
        function handleFileSelect(event) {
            const files = event.target.files;
            console.log('Selected files:', files.length, Array.from(files).map(f => f.name));
            handleFiles(files);
        }
        function handleFiles(files) {
            for (let file of files) {
                if (!uploadedFiles.find(f => f.name === file.name)) {
                    uploadedFiles.push(file);
                    console.log('Added file:', file.name);
                } else {
                    console.log('Duplicate file ignored:', file.name);
                }
            }
            updateFilesList();
            updateProcessButton();
        }
        function triggerFileInput() {
            const fileInput = document.getElementById('fileInput');
            console.log('Triggering file input click');
            fileInput.click();
        }
        function updateFilesList() {
            const filesList = document.getElementById('filesList');
            const emptyState = document.getElementById('emptyState');
            if (uploadedFiles.length === 0) {
                filesList.classList.add('hidden');
                emptyState.classList.remove('hidden');
                return;
            }
            filesList.classList.remove('hidden');
            emptyState.classList.add('hidden');
            filesList.innerHTML = uploadedFiles.map((file, index) => {
                const fileInfo = getFileType(file.name);
                const fileSize = (file.size / 1024).toFixed(1) + ' KB';
                return `<div class="file-item bg-white bg-opacity-10 rounded-lg p-4 border border-white border-opacity-20">
                    <div class="flex items-center justify-between mb-2">
                        <div class="flex items-center">
                            <i class="material-icons text-2xl mr-2 text-white">${fileInfo.icon}</i>
                            <div>
                                <h6 class="text-white font-semibold truncate" title="${file.name}">${file.name}</h6>
                                <p class="text-white text-opacity-70 text-sm">${fileSize}</p>
                            </div>
                        </div>
                        <button class="btn-small waves-effect waves-light red" onclick="removeFile(${index})"><i class="material-icons">close</i></button>
                    </div>
                    <div class="flex justify-between items-center">
                        <span class="chip ${fileInfo.color} white-text">${fileInfo.type}</span>
                        <span class="text-white text-opacity-50 text-xs">${new Date(file.lastModified).toLocaleDateString()}</span>
                    </div>
                </div>`;
            }).join('');
            console.log('Updated files list with', uploadedFiles.length, 'files');
        }
        function removeFile(index) {
            console.log('Removing file at index:', index);
            uploadedFiles.splice(index, 1);
            updateFilesList();
            updateProcessButton();
        }
        function updateProcessButton() {
            const processBtn = document.getElementById('processBtn');
            const previewBtn = document.getElementById('previewBtn');
            const hasFiles = uploadedFiles.length > 0;
            processBtn.disabled = !hasFiles;
            previewBtn.disabled = !hasFiles;
            if (hasFiles) {
                processBtn.classList.remove('disabled');
                previewBtn.classList.remove('disabled');
            } else {
                processBtn.classList.add('disabled');
                previewBtn.classList.add('disabled');
            }
            console.log('Process button state:', !hasFiles ? 'disabled' : 'enabled');
        }
        async function previewData() {
            if (isPreviewLoading) {
                console.log('Preview already in progress, ignoring click');
                return;
            }
            isPreviewLoading = true;
            console.log('Preview data triggered');

            const previewSection = document.getElementById('previewSection');
            const previewContent = document.getElementById('previewContent');
            const loadingSpinner = document.getElementById('loadingSpinner');
            const previewData = document.getElementById('previewData');

            console.log('Setting previewSection visible');
            previewSection.classList.remove('hidden');
            loadingSpinner.classList.remove('hidden');
            previewData.classList.add('hidden');

            // Destroy existing charts
            Object.keys(charts).forEach(key => {
                if (charts[key]) {
                    console.log(`Destroying chart: ${key}`);
                    charts[key].destroy();
                    charts[key] = null;
                }
            });

            const formData = new FormData();
            uploadedFiles.forEach(file => {
                formData.append('files', file);
                console.log('Appending file to formData:', file.name);
            });

            try {
                console.log('Fetching preview data');
                const response = await fetch('/preview', { method: 'POST', body: formData });
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.error || 'Failed to fetch preview data');
                }
                const data = await response.json();
                console.log('Preview data received:', data);

                // Update summary table with N/A for empty values
                document.getElementById('totalClaims').textContent = data.total_claims || 'N/A';
                document.getElementById('totalPatients').textContent = data.total_patients || 'N/A';
                document.getElementById('dateRange').textContent = data.date_range || 'N/A';
                document.getElementById('totalAmount').textContent = data.total_amount || 'N/A';

                // Update sample claims table with N/A for empty values
                if (data.sample_claims && data.sample_claims.length > 0) {
                    const headers = Object.keys(data.sample_claims[0]);
                    document.getElementById('tableHeaders').innerHTML = headers.map(h => `<th>${h}</th>`).join('');
                    document.getElementById('tableBody').innerHTML = data.sample_claims.map(row => {
                        return `<tr>${headers.map(h => `<td>${row[h] || 'N/A'}</td>`).join('')}</tr>`;
                    }).join('');
                } else {
                    console.warn('No sample claims available');
                    document.getElementById('tableHeaders').innerHTML = '<th>No Data</th>';
                    document.getElementById('tableBody').innerHTML = '<tr><td>No claims to display</td></tr>';
                }

                // Specialty Chart with N/A for empty labels
                if (Object.keys(data.claims_by_specialty || {}).length > 0) {
                    const specialtyCtx = document.getElementById('specialtyChart').getContext('2d');
                    charts.specialty = new Chart(specialtyCtx, {
                        type: 'bar',
                        data: {
                            labels: Object.keys(data.claims_by_specialty).map(label => label || 'N/A'),
                            datasets: [{
                                label: 'Claims by Specialty',
                                data: Object.values(data.claims_by_specialty),
                                backgroundColor: 'rgba(79, 70, 229, 0.6)',
                                borderColor: 'rgba(79, 70, 229, 1)',
                                borderWidth: 1
                            }]
                        },
                        options: {
                            indexAxis: 'y',
                            scales: {
                                x: { beginAtZero: true, title: { display: true, text: 'Claims', color: '#ffffff' } },
                                y: { title: { display: true, text: 'Specialty', color: '#ffffff' } }
                            },
                            plugins: {
                                legend: { display: false },
                                title: { display: true, text: 'Claims by Specialty', color: '#ffffff', font: { size: 14 } }
                            }
                        }
                    });
                } else {
                    console.warn('No specialty data for chart');
                }

                // Procedure Chart with N/A for empty labels
                if (data.top_procedures && data.top_procedures.length > 0) {
                    const procedureCtx = document.getElementById('procedureChart').getContext('2d');
                    charts.procedure = new Chart(procedureCtx, {
                        type: 'bar',
                        data: {
                            labels: data.top_procedures.map(p => p.procedure || 'N/A'),
                            datasets: [{
                                label: 'Top Procedures',
                                data: data.top_procedures.map(p => p.count || 0),
                                backgroundColor: 'rgba(249, 115, 22, 0.6)',
                                borderColor: 'rgba(249, 115, 22, 1)',
                                borderWidth: 1
                            }]
                        },
                        options: {
                            indexAxis: 'y',
                            scales: {
                                x: { beginAtZero: true, title: { display: true, text: 'Claims', color: '#ffffff' } },
                                y: { title: { display: true, text: 'Procedure', color: '#ffffff' } }
                            },
                            plugins: {
                                legend: { display: false },
                                title: { display: true, text: 'Top Procedures', color: '#ffffff', font: { size: 14 } }
                            }
                        }
                    });
                } else {
                    console.warn('No procedure data for chart');
                }

                // Gender Chart with N/A for empty labels
                if (Object.keys(data.claims_by_gender || {}).length > 0) {
                    const genderCtx = document.getElementById('genderChart').getContext('2d');
                    charts.gender = new Chart(genderCtx, {
                        type: 'pie',
                        data: {
                            labels: Object.keys(data.claims_by_gender).map(label => label || 'N/A'),
                            datasets: [{
                                label: 'Claims by Gender',
                                data: Object.values(data.claims_by_gender),
                                backgroundColor: ['rgba(236, 72, 153, 0.6)', 'rgba(59, 130, 246, 0.6)', 'rgba(234, 179, 8, 0.6)'],
                                borderColor: ['rgba(236, 72, 153, 1)', 'rgba(59, 130, 246, 1)', 'rgba(234, 179, 8, 1)'],
                                borderWidth: 1
                            }]
                        },
                        options: {
                            plugins: {
                                legend: { position: 'bottom', labels: { color: '#ffffff', font: { size: 12 } } },
                                title: { display: true, text: 'Claims by Gender', color: '#ffffff', font: { size: 14 } }
                            }
                        }
                    });
                } else {
                    console.warn('No gender data for chart');
                }

                // State Chart with N/A for empty labels
                if (Object.keys(data.claims_by_state || {}).length > 0) {
                    const stateCtx = document.getElementById('stateChart').getContext('2d');
                    charts.state = new Chart(stateCtx, {
                        type: 'bar',
                        data: {
                            labels: Object.keys(data.claims_by_state).map(label => label || 'N/A'),
                            datasets: [{
                                label: 'Claims by State',
                                data: Object.values(data.claims_by_state),
                                backgroundColor: 'rgba(16, 185, 129, 0.6)',
                                borderColor: 'rgba(16, 185, 129, 1)',
                                borderWidth: 1
                            }]
                        },
                        options: {
                            indexAxis: 'y',
                            scales: {
                                x: { beginAtZero: true, title: { display: true, text: 'Claims', color: '#ffffff' } },
                                y: { title: { display: true, text: 'State', color: '#ffffff' } }
                            },
                            plugins: {
                                legend: { display: false },
                                title: { display: true, text: 'Claims by State', color: '#ffffff', font: { size: 14 } }
                            }
                        }
                    });
                } else {
                    console.warn('No state data for chart');
                }

                console.log('Showing preview data');
                loadingSpinner.classList.add('hidden');
                previewData.classList.remove('hidden');
                console.log('Preview rendering complete');
            } catch (error) {
                console.error('Preview error:', error);
                loadingSpinner.classList.add('hidden');
                previewData.classList.remove('hidden');
                document.getElementById('totalClaims').textContent = 'Error';
                document.getElementById('totalPatients').textContent = 'Error';
                document.getElementById('dateRange').textContent = 'Error';
                document.getElementById('totalAmount').textContent = 'Error';
                document.getElementById('tableHeaders').innerHTML = '<th>Error</th>';
                document.getElementById('tableBody').innerHTML = '<tr><td>Failed to load data</td></tr>';
                M.toast({html: 'Error: ' + error.message, classes: 'red'});
            } finally {
                isPreviewLoading = false;
                console.log('Preview loading state reset');
            }
        }
        async function processFiles() {
            console.log('Process files triggered');
            const progressSection = document.getElementById('progressSection');
            const progressBar = document.getElementById('progressBar');
            const progressText = document.getElementById('progressText');
            progressSection.classList.remove('hidden');
            const formData = new FormData();
            uploadedFiles.forEach(file => {
                formData.append('files', file);
                console.log('Appending file to process:', file.name);
            });
            formData.append('outputFormat', document.getElementById('outputFormat').value);
            formData.append('dateFormat', document.getElementById('dateFormat').value);
            try {
                progressText.textContent = 'Uploading files...'; progressBar.style.width = '20%';
                const response = await fetch('/process', { method: 'POST', body: formData });
                progressText.textContent = 'Processing data...'; progressBar.style.width = '60%';
                if (response.ok) {
                    progressText.textContent = 'Generating report...'; progressBar.style.width = '90%';
                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `medical_claims_report.${document.getElementById('outputFormat').value}`;
                    a.click();
                    window.URL.revokeObjectURL(url);
                    progressText.textContent = 'Complete!'; progressBar.style.width = '100%';
                    setTimeout(() => { progressSection.classList.add('hidden'); progressBar.style.width = '0%'; }, 2000);
                    M.toast({html: 'File processed successfully!', classes: 'green'});
                } else {
                    const errorData = await response.json();
                    throw new Error(errorData.error || 'Processing failed');
                }
            } catch (error) {
                console.error('Process error:', error);
                progressSection.classList.add('hidden');
                progressBar.style.width = '0%';
                M.toast({html: 'Error processing files: ' + error.message, classes: 'red'});
            }
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/preview', methods=['POST'])
def preview():
    try:
        files_data = {}
        for file in request.files.getlist('files'):
            if file.filename:
                filename = secure_filename(file.filename)
                files_data[filename] = file.read()
        
        if not files_data:
            return jsonify({'error': 'No files uploaded'}), 400
        
        records_df = process_medical_claims(files_data)
        if records_df.empty:
            return jsonify({'error': 'No data could be processed'}), 400
        
        analytics = calculate_claim_analytics(records_df)
        sample_claims = records_df.head(5).to_dict('records')
        analytics['sample_claims'] = sample_claims
        
        return jsonify(analytics)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/process', methods=['POST'])
def process():
    try:
        files_data = {}
        for file in request.files.getlist('files'):
            if file.filename:
                filename = secure_filename(file.filename)
                files_data[filename] = file.read()
        
        if not files_data:
            return jsonify({'error': 'No files uploaded'}), 400
        
        output_format = request.form.get('outputFormat', 'csv')
        date_format = request.form.get('dateFormat', 'YYYY-MM-DD')
        
        result_df = process_medical_claims(files_data, date_format)
        if result_df.empty:
            return jsonify({'error': 'No data could be processed'}), 400
        
        output = io.BytesIO()
        if output_format == 'csv':
            result_df.to_csv(output, index=False)
            mimetype = 'text/csv'
            filename = 'medical_claims_report.csv'
        elif output_format == 'excel':
            result_df.to_excel(output, index=False, engine='openpyxl')
            mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            filename = 'medical_claims_report.xlsx'
        elif output_format == 'json':
            result_df.to_json(output, orient='records', indent=2)
            mimetype = 'application/json'
            filename = 'medical_claims_report.json'
        else:
            return jsonify({'error': 'Invalid output format'}), 400
        output.seek(0)
        return send_file(
            output,
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    required_packages = ['flask', 'pandas', 'openpyxl', 'werkzeug']
    print("Medical Claims File Processor")
    print("=" * 50)
    print("Required Python packages:")
    for package in required_packages:
        print(f"  - {package}")
    print("\nTo install: pip install " + " ".join(required_packages))
    print("\nStarting server...")
    print("Access the application at: http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=5000)