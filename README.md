# Medical Claims File Processor - Setup Guide

## Overview
This is a beautiful web application for processing medical claims files. It features a modern glass-morphism design with drag-and-drop file upload, real-time processing feedback, and multiple output formats.

## Features
- 🎨 **Beautiful UI**: Modern gradient background with glass-morphism effects
- 📁 **Drag & Drop**: Easy file uploading with visual feedback
- 📊 **Multiple Formats**: Support for Excel (.xlsx), JSON, and CSV files
- 🔄 **Real-time Processing**: Progress bars and status updates
- 📈 **Multiple Outputs**: Generate CSV, Excel, or JSON reports
- 🎯 **Smart Processing**: Automatically detects and processes medical claims data

## Requirements

Create a `requirements.txt` file:

```txt
Flask==2.3.3
pandas==2.1.4
openpyxl==3.1.2
Werkzeug==2.3.7
```

## Installation Steps

### 1. Create Project Directory
```bash
mkdir medical-claims-processor
cd medical-claims-processor
```

### 2. Create Virtual Environment (Recommended)
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install flask pandas openpyxl werkzeug
```

### 4. Create the Python File
Save the Python backend code as `app.py` in your project directory.

### 5. Run the Application
```bash
python app.py
```

### 6. Access the Application
Open your web browser and go to: `http://localhost:5000`

## File Structure
```
medical-claims-processor/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

## How to Use

### 1. Upload Files
- Click "Choose Files" or drag and drop files into the upload zone
- The application expects these files:
  - `records.xlsx` - Excel file with medical records
  - `facilities.json` - JSON file with facility information
  - `providers.json` - JSON file with provider information  
  - `procedures.json` - JSON file with procedure information

### 2. Configure Output
- **Output Format**: Choose between CSV, Excel, or JSON
- **Date Format**: Select your preferred date format (YYYY-MM-DD, MM/DD/YYYY, DD/MM/YYYY)

### 3. Process Files
- Click "Process Files" to start processing
- Watch the progress bar for real-time updates
- The processed file will automatically download when complete



## Troubleshooting

### Common Issues:

1. **Port Already in Use**
   ```bash
   # Change port in app.py, last line:
   app.run(debug=True, host='0.0.0.0', port=5001)  # Change 5000 to 5001
   ```

2. **File Upload Errors**
   - Ensure files are in the correct format (.xlsx for records, .json for others)
   - Check that file names contain the expected keywords (records, facilities, providers, procedures)

3. **Processing Errors**
   - Verify your data structure matches the expected format
   - Check the browser console for detailed error messages

### Development Mode
The application runs in debug mode by default, which provides:
- Automatic reloading when code changes
- Detailed error messages
- Hot reloading for development

### Production Deployment
For production use, consider:
- Setting `debug=False`
- Using a production WSGI server like Gunicorn
- Adding proper error handling and logging
- Implementing file size limits and validation

## Customization

### Styling
The UI uses Tailwind CSS and Materialize CSS. You can customize:
- Colors in the gradient background
- Glass-morphism effects
- Component styling

### Processing Logic
Modify the `process_medical_claims()` function to:
- Handle different data structures
- Add custom validation rules
- Implement additional processing logic

### File Support
Extend file support by modifying the upload handlers to accept additional formats like:
- `.csv` files for records
- `.xml` files for structured data
- Custom file formats

## Support

If you encounter issues:
1. Check the console output for error messages
2. Verify your data structure matches the expected format
3. Ensure all required files are uploaded
4. Check that Python dependencies are properly installed
