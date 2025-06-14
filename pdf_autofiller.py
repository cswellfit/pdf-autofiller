import argparse
import os
import yaml
from PyPDF2 import PdfReader
import pdfrw
import openai

def load_config(config_path="config.yaml"):
    """Loads OpenAI configuration from a YAML file."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found at: {config_path}")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)

def get_field_type_from_ai(field_name, client, model):
    """
    Uses OpenAI's ChatCompletion to determine the most appropriate data type for a given field name.
    """
    field_categories = [
        "name", "first_name", "last_name", "phone_number", "email", "address",
        "city", "state", "zip_code", "country", "company", "job_title", "date",
        "vehicle_year", "vehicle_make", "vehicle_model", "vin", "license_plate",
        "currency_amount", "boolean", "text"
    ]
    prompt = f"""
    You are an expert at categorizing PDF form fields into specific data types.
    Based on the field name "{field_name}", what is the most specific data type from the following list?
    List: {', '.join(field_categories)}
    Respond with only a single category from the list.
    """
    try:
        response = client.chat.completions.create(
            model=model, messages=[{"role": "system", "content": "You are an expert at categorizing PDF form fields."}, {"role": "user", "content": prompt}], temperature=0.0)
        category = response.choices[0].message.content.strip().lower().replace("_", " ")
        return category if category.replace(" ", "_") in field_categories else "text"
    except Exception as e:
        print(f"An error occurred while contacting OpenAI for field detection: {e}")
        return "text"

def get_data_from_ai(field_name, field_type, client, model):
    """
    Uses OpenAI's ChatCompletion to generate a realistic value for a given field type.
    """
    prompt = f"""
    You are an expert at generating realistic sample data for filling out forms.
    Based on the field name "{field_name}" and its determined type "{field_type}", generate a single, realistic data value.
    - Your response must be ONLY the data value itself, with no extra text, labels, or quotation marks.
    - For a 'date', use YYYY-MM-DD format.
    - For a 'boolean', respond with either 'Yes' or 'Off'.
    - For a 'currency_amount', provide a number like '12345.00'.
    Generate a value for a field of type: {field_type}
    """
    try:
        response = client.chat.completions.create(
            model=model, messages=[{"role": "system", "content": "You are a data generation engine."}, {"role": "user", "content": prompt}], temperature=0.7)
        data_value = response.choices[0].message.content.strip(' "')
        if field_type == 'boolean':
            return True if 'yes' in data_value.lower() else False
        return data_value
    except Exception as e:
        print(f"An error occurred while contacting OpenAI for data generation: {e}")
        return ""


def fill_pdf_form(input_pdf, data_to_fill):
    """
    Fills a PDF form using the pdfrw library.
    """
    template_pdf = pdfrw.PdfReader(input_pdf)
    for page in template_pdf.pages:
        annotations = page.get('/Annots')
        if annotations is None:
            continue
        for annotation in annotations:
            if annotation.get('/Subtype') == '/Widget' and annotation.get('/T'):
                field_name = annotation['/T'][1:-1]
                if field_name in data_to_fill:
                    field_value = data_to_fill[field_name]
                    if isinstance(field_value, bool):
                        if field_value:
                            annotation.update(pdfrw.PdfDict(V=pdfrw.PdfName('Yes'), AS=pdfrw.PdfName('Yes')))
                        else:
                            annotation.update(pdfrw.PdfDict(V=pdfrw.PdfName('Off'), AS=pdfrw.PdfName('Off')))
                    else:
                        annotation.update(pdfrw.PdfDict(V=str(field_value)))
    if template_pdf.Root.AcroForm:
        template_pdf.Root.AcroForm.update(pdfrw.PdfDict(NeedAppearances=pdfrw.PdfObject('true')))
    return template_pdf

def main():
    parser = argparse.ArgumentParser(description="Fill a PDF form with random data using AI field detection and generation.")
    parser.add_argument("--input-file", required=True, help="Path to the fillable PDF form.")
    parser.add_argument("--output-prefix", default="filled_document", help="Prefix for the output PDF files.")
    parser.add_argument("--output-number", type=int, default=1, help="Number of filled documents to generate.")
    parser.add_argument("--config", default="config.yaml", help="Path to the OpenAI configuration file.")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        openai_config = config.get("openai", {})
        if not openai_config.get("api_key"):
            raise ValueError("OpenAI API key is missing from config.yaml")
        client = openai.OpenAI(api_key=openai_config["api_key"], base_url=openai_config.get("endpoint_url") or None)
        model_to_use = openai_config.get("model", "gpt-3.5-turbo")
        print(f"Using OpenAI model: {model_to_use}")
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        return

    if not os.path.exists(args.input_file):
        print(f"Error: Input file not found at '{args.input_file}'")
        return

    print(f"Reading fields from '{args.input_file}'...")
    reader = PdfReader(args.input_file)
    fields = reader.get_fields()
    if not fields:
        print("No fields to fill in the provided PDF.")
        return

    print(f"Found {len(fields)} fields. Detecting field types and generating data with AI...")

    for i in range(1, args.output_number + 1):
        print(f"\n--- Generating Document {i} ---")
        data_to_fill = {}
        for field_name in fields.keys():
            field_type = get_field_type_from_ai(field_name, client, model_to_use)
            print(f"  - Field: '{field_name}' -> AI Detected Type: '{field_type}'")
            
            data_value = get_data_from_ai(field_name, field_type, client, model_to_use)
            print(f"    - AI Generated Data: '{data_value}'")
            
            data_to_fill[field_name] = data_value

        filled_template = fill_pdf_form(args.input_file, data_to_fill)
        output_filename = f"{args.output_prefix}-{i}.pdf"
        pdfrw.PdfWriter().write(output_filename, filled_template)
        print(f"\nSuccessfully generated '{output_filename}'")

if __name__ == "__main__":
    main()
