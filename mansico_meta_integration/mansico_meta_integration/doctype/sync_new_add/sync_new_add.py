# Copyright (c) 2023, mansy and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


@frappe.whitelist()
def get_credentials():
    return frappe.get_doc("Meta Facebook Settings")


import requests
import json
import re
import hashlib


# Max length for the generated fieldname. Frappe/MySQL column names are capped
# at 64 chars and Frappe's Custom Field validator rejects names at that limit,
# so we keep a small safety margin.
_MAX_FIELDNAME_LEN = 60


def _custom_fieldname_from_key(key):
    """Build a safe Frappe fieldname for a Meta custom question key.

    - Prefixes with `custom_` so the auto-created field is clearly namespaced.
    - Replaces any non-alphanumeric character with `_`.
    - Collapses repeated underscores and trims trailing ones.
    - If the sanitized name is too long, truncates and appends a short hash
      of the original key to keep the fieldname unique and reproducible.
    """
    if not key:
        return None
    safe = re.sub(r"[^0-9a-zA-Z]+", "_", str(key)).strip("_").lower()
    if not safe:
        return None
    if not safe.startswith("custom_"):
        safe = "custom_" + safe
    if len(safe) > _MAX_FIELDNAME_LEN:
        digest = hashlib.md5(str(key).encode("utf-8")).hexdigest()[:6]
        safe = safe[: _MAX_FIELDNAME_LEN - 7].rstrip("_") + "_" + digest
    return safe.rstrip("_")


def _ensure_lead_custom_field(lead_doctype, fieldname, label, field_type=None):
    """Create a Custom Field on the Lead doctype if it does not exist yet."""
    if not fieldname:
        return
    if frappe.get_meta(lead_doctype).has_field(fieldname):
        return
    # Map Meta field types to Frappe fieldtypes; default to Data.
    ft_map = {
        "DATE_TIME": "Datetime",
        "DATE": "Date",
        "NUMBER": "Data",
    }
    fieldtype = ft_map.get(field_type, "Data")
    try:
        frappe.get_doc(
            {
                "doctype": "Custom Field",
                "dt": lead_doctype,
                "fieldname": fieldname,
                "label": label or fieldname,
                "fieldtype": fieldtype,
                "insert_after": "custom_lead_json",
            }
        ).insert(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        # Another process created it concurrently; ignore.
        pass


def _normalize_phone(value):
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    digit_map = str.maketrans(
        {
            "٠": "0",
            "١": "1",
            "٢": "2",
            "٣": "3",
            "٤": "4",
            "٥": "5",
            "٦": "6",
            "٧": "7",
            "٨": "8",
            "٩": "9",
            "۰": "0",
            "۱": "1",
            "۲": "2",
            "۳": "3",
            "۴": "4",
            "۵": "5",
            "۶": "6",
            "۷": "7",
            "۸": "8",
            "۹": "9",
        }
    )
    s = s.translate(digit_map)
    s = re.sub(r"[\s\-\(\)\.]+", "", s)
    if s.startswith("+"):
        s = "+" + re.sub(r"\D", "", s[1:])
    else:
        s = re.sub(r"\D", "", s)
    return s or None


def _truncate_to_field_length(doctype, fieldname, value):
    if value is None:
        return None
    if not fieldname:
        return value
    if not isinstance(value, str):
        return value
    v = frappe.utils.strip_html(value).strip()
    df = frappe.get_meta(doctype).get_field(fieldname)
    if not df:
        return v
    if df.fieldtype in ("Text", "Long Text", "Code"):
        return v
    max_len = df.length
    if not max_len:
        if df.fieldtype == "Small Text":
            max_len = 255
        elif df.fieldtype in ("Data", "Link", "Select", "Phone", "Email", "Dynamic Link"):
            max_len = 140
    if max_len and len(v) > max_len:
        return v[:max_len]
    return v


class Request:
    def __init__(self, url, version, page_id, f_payload=None, params=None):
        self.url = url
        self.version = "v" + str(version)
        self.page_id = page_id
        self.f_payload = f_payload
        self.params = params

    @property
    def get_url(self):
        return self.url + "/" + self.version + "/" + self.page_id


class RequestPageAccessToken:
    def __init__(self, request):
        self.request = request

    def get_page_access_token(self):
        response = requests.get(
            self.request.get_url, params=self.request.params, json=self.request.params
        )

        if frappe._dict(response.json()).get("error"):
            _error_message = ""
            _error_message += "url" + " : " + str(self.request.get_url) + "<br>"
            _error_message += "params" + " : " + str(self.request.params) + "<br>"
            _error_message += "<br>"
            for key in frappe._dict(response.json()).get("error").keys():
                _error_message += (
                    key
                    + " : "
                    + str(frappe._dict(response.json()).get("error").get(key))
                    + "<br>"
                )
            frappe.throw(_error_message, title="Error")
        else:
            self.page_access_token = frappe._dict(response.json()).get("access_token")
            return self.page_access_token


class RequestLeadGenFroms:
    def __init__(self, request):
        self.request = request

    def get_lead_forms(self):
        response = requests.get(
            self.request.get_url, params=self.request.params, json=self.request.params
        )
        if frappe._dict(response.json()).get("error"):
            _error_message = ""
            _error_message += "url" + " : " + str(self.request.get_url) + "<br>"
            _error_message += "params" + " : " + str(self.request.params) + "<br>"
            _error_message += "<br>"
            for key in frappe._dict(response.json()).get("error").keys():
                _error_message += (
                    key
                    + " : "
                    + str(frappe._dict(response.json()).get("error").get(key))
                    + "<br>"
                )
            frappe.throw(_error_message, title="Error")
        else:
            self.lead_forms = frappe._dict(response.json())
            return self.lead_forms


class AppendForms:
    def __init__(self, lead_forms, doc):
        self.lead_forms = lead_forms
        self.doc = doc

    def append_forms(self):
        if self.doc.force_fetch:
            self.doc.set("table_hsya", [])

            for lead_form in self.lead_forms.get("data"):
                self.doc.append(
                    "table_hsya",
                    {
                        "form_id": lead_form.get("id"),
                        "form_name": lead_form.get("name"),
                        "created_time": lead_form.get("created_time"),
                        "leads_count": lead_form.get("leads_count"),
                        "page": lead_form.get("page"),
                        "questions": frappe._dict(
                            {"questions": lead_form.get("questions")}
                        ),
                    },
                )
        if self.doc.fetch_map_lead_fields:
            self.doc.set("map_lead_fields", [])
            form_fields = []  # Initialize an empty list to track form fields
            for lead in self.doc.table_hsya:
                self.set_map_lead_fields(
                    json.loads(lead.questions).get("questions")
                    if isinstance(lead.questions, str)
                    else lead.questions.get("questions"),
                    form_fields,
                )

    # Mapping from Meta question "type" to a standard ERPNext Lead field.
    STANDARD_TYPE_TO_LEAD_FIELD = {
        "EMAIL": "email_id",
        "FULL_NAME": "first_name",
        "FIRST_NAME": "first_name",
        "LAST_NAME": "last_name",
        "PHONE": "mobile_no",
        "PHONE_NUMBER": "mobile_no",
        "WORK_PHONE_NUMBER": "phone",
        "JOB_TITLE": "job_title",
        "COMPANY_NAME": "company_name",
        "CITY": "city",
        "COUNTRY": "country",
        "STATE": "state",
    }

    KEY_TO_LEAD_FIELD = {
        "full_name": "first_name",
        "fullname": "first_name",
        "fullname_ar": "first_name",
        "name": "first_name",
        "phone": "mobile_no",
        "mobile": "mobile_no",
        "mobile_no": "mobile_no",
        "work_phone_number": "phone",
        "work_phone": "phone",
        "email": "email_id",
        "email_id": "email_id",
    }

    def set_map_lead_fields(self, questions, form_fields):
        for question in questions:
            key = question.get("key")
            qtype = question.get("type")
            if key in form_fields:
                continue

            # Normalize key (Meta can send keys like "full name").
            key_norm = re.sub(r"[^0-9a-zA-Z]+", "_", str(key or "")).strip("_").lower()

            # Pick a target Lead field:
            # - Known Meta types -> standard Lead field.
            # - Anything else (CUSTOM, unknown) -> sanitized custom_<key>
            #   so it maps onto an auto-created Custom Field on Lead.
            standard_field = self.KEY_TO_LEAD_FIELD.get(key_norm) or self.STANDARD_TYPE_TO_LEAD_FIELD.get(qtype)
            if standard_field:
                lead_field = standard_field
            else:
                lead_field = _custom_fieldname_from_key(key)
                # Skip questions whose key cannot be turned into a valid
                # Frappe fieldname (empty/invalid key). Otherwise the child
                # row would be created without a `lead_field` and fail the
                # mandatory validation on `Map Lead Field`.
                if not lead_field:
                    continue
                # Make sure the target Custom Field exists on the Lead doctype
                # before we try to write to it later during lead creation.
                _ensure_lead_custom_field(
                    self.doc.lead_doctype_name,
                    lead_field,
                    question.get("label"),
                    qtype,
                )

            self.doc.append(
                "map_lead_fields",
                {
                    "lead_field": lead_field,
                    "form_field": key,
                    "form_field_label": question.get("label"),
                    "form_field_type": qtype,
                },
            )
            form_fields.append(key)


class ServerScript:
    def __init__(self, doc):
        self.doc = doc

    def create_server_script(self):
        self.server_script = frappe.get_doc(
            {
                "doctype": "Server Script",
                "name": str(str(self.doc.name).replace("-", "_")).lower(),
                "script_type": "Scheduler Event",
                "event_frequency": self.doc.event_frequency,
                "module": "Mansico Meta Integration",
                "script": self.generate_script(),
            }
        )

    def generate_script(self):
        _script = ""

        _script += """from mansico_meta_integration.mansico_meta_integration.doctype.sync_new_add.sync_new_add import FetchLeads\n"""
        _script += """import frappe\n"""
        _script += """fetch = FetchLeads("{0}")\n""".format(self.doc.name)
        _script += """fetch.fetch_leads()\n"""
        return _script


class RequestSendLead:
    def __init__(self, request):
        self.request = request

    def send_lead(self):
        response = requests.post(
            self.request.get_url,
            params=self.request.params,
            json=self.request.f_payload,
        )
        if frappe._dict(response.json()).get("error"):
            error_message = ""
            error_message += "url" + " : " + str(self.request.get_url) + "<br>"
            error_message += "params" + " : " + str(self.request.params) + "<br>"
            error_message += "<br>"
            for key in json.dumps(response.json()).get("error").keys():
                error_message += (
                    key
                    + " : "
                    + str(json.dumps(response.json()).get("error").get(key))
                    + "<br>"
                )
            frappe.throw(error_message, title="Error")
        else:
            return json.dumps(response.json())


class FetchLeads:
    def __init__(self, name):
        self.name = name

    @property
    def get_form_ids(self):
        form_ids = []
        for form in self.doc.table_hsya:
            form_ids.append(form.form_id)
        return form_ids

    @frappe.whitelist()
    def fetch_leads(self):
        self.doc = frappe.get_doc("Sync New Add", self.name)
        self.page = frappe.get_doc("Page ID", self.doc.page_id)
        self.form_ids = self.get_form_ids
        for form_id in self.form_ids:
            defaults = get_credentials()
            #  init Request
            request = Request(
                defaults.api_url,
                defaults.graph_api_version,
                self.doc.page_id,
                None,
                params={
                    "fields": "access_token",
                    "transport": "cors",
                    "access_token": defaults.access_token,
                },
            )
            # init RequestPageAccessToken
            request_page_access_token = RequestPageAccessToken(request)
            # get page access token
            request_page_access_token.get_page_access_token()
            # init Request
            request = Request(
                defaults.api_url,
                defaults.graph_api_version,
                form_id + "/leads",
                None,
                params={
                    "access_token": request_page_access_token.page_access_token,
                    "fields": "ad_id,ad_name,adset_id,adset_name,\
                campaign_id,campaign_name,created_time,custom_disclaimer_responses,\
                    field_data,form_id,id,home_listing,is_organic,partner_name,\
                        platform,post,retailer_item_id,vehicle",
                },
            )
            # init RequestLeadGenFroms
            request_lead_gen_forms = RequestLeadGenFroms(request)
            # get lead forms
            request_lead_gen_forms.get_lead_forms()

            if request_lead_gen_forms.lead_forms.get("data"):
                # use self.lead_forms
                # fetch all leads then create them using create_lead
                # filter leads by created_time and id to avoid duplication
                self.paginate_lead_forms(request_lead_gen_forms.lead_forms)

    def paginate_lead_forms(self, lead_forms):
        if lead_forms.paging.get("next"):
            self.create_lead(lead_forms.get("data"))
            next_page = lead_forms.paging.get("next")
            response = requests.get(next_page)
            lead_forms = frappe._dict(response.json())
            return self.paginate_lead_forms(lead_forms)
        else:
            if lead_forms:
                self.create_lead(lead_forms.get("data"))
            return lead_forms

    def create_lead(self, leads):
        import traceback

        for lead in leads:
            # Initialize an empty dictionary to store lead data dynamically
            lead_data = {}
            # Loop through the field_data and extract the values dynamically
            for field in lead.get("field_data", []):
                field_name = field.get("name")
                field_value = field.get("values", [None])[
                    0
                ]  # Get the first value or None if no value is present

                # Check if the field_name exists in the map_lead_fields of the current doc
                for mapping in self.doc.map_lead_fields:
                    if mapping.get("form_field") == field_name:
                        # Dynamically map field_data to the Lead fields based on map_lead_fields
                        target_field = mapping.get("lead_field")
                        if target_field in ("phone", "mobile_no"):
                            field_value = _normalize_phone(field_value)
                            if not field_value:
                                continue
                        field_value = _truncate_to_field_length(
                            self.doc.lead_doctype_name, target_field, field_value
                        )
                        lead_data[target_field] = field_value

            if lead.get("id") and not frappe.db.exists(
                self.doc.lead_doctype_name, {"custom_meta_lead_id": lead.get("id")}
            ):
                try:
                    # Create a new Lead document dynamically based on available fields
                    new_lead_data = {
                        "doctype": self.doc.lead_doctype_name,
                        "custom_meta_lead_id": lead.get("id"),
                        "custom_lead_json": frappe._dict(lead),
                    }

                    # Dynamically populate lead fields from lead_data
                    for field_name, field_value in lead_data.items():
                        new_lead_data[field_name] = field_value

                    try:
                        new_lead = frappe.get_doc(new_lead_data)
                        new_lead.insert(ignore_permissions=True)
                    except frappe.DuplicateEntryError as dup_err:
                        # Duplicate Contact name (ERPNext auto-creates Contact from Lead).
                        # Rollback and retry while bypassing auto-Contact creation.
                        frappe.db.rollback()
                        from erpnext.crm.doctype.lead.lead import Lead as _ERPLead
                        _orig = _ERPLead.create_contact
                        _ERPLead.create_contact = lambda self: None
                        try:
                            new_lead = frappe.get_doc(new_lead_data)
                            new_lead.insert(ignore_permissions=True)
                        finally:
                            _ERPLead.create_contact = _orig
                    frappe.db.commit()

                    # Optionally, create the lead in Facebook
                    FetchLeads.create_lead_in_facebook(new_lead, self.page)

                except Exception as e:
                    # Rollback failed transaction to release locks
                    frappe.db.rollback()
                    # Log errors and traceback for better debugging
                    frappe.log_error("Error in Lead Creation", str(e))
                    frappe.log_error("Traceback", str(traceback.format_exc()))
                    frappe.log_error("Lead Data", str(lead_data))

    @staticmethod
    def create_lead_in_facebook(lead, page):
        import datetime
        import json
        from mansico_meta_integration.mansico_meta_integration.doctype.sync_new_add.meta_integraion_objects import (
            UserData,
            CustomData,
            Payload,
        )

        now = datetime.datetime.now()
        unixtime = int(now.timestamp())

        if lead.custom_meta_lead_id:
            # Create UserData and CustomData objects
            user_data = UserData(lead.custom_meta_lead_id)
            custom_data = CustomData("crm", "ERP Next")

            # Create Payload object
            payload = Payload(
                event_name=lead.status,
                event_time=unixtime,
                action_source="system_generated",
                user_data=user_data,
                custom_data=custom_data,
            )

            # Convert Payload to dictionary
            f_payload = {"data": [payload.to_dict()]}

            # Send request to Facebook
            defaults = get_credentials()
            request = Request(
                defaults.api_url,
                defaults.graph_api_version,
                page.pixel_id + "/events",
                f_payload,
                params={"access_token": page.pixel_access_token},
            )

            # Send the lead
            request_send_lead = RequestSendLead(request)
            response = request_send_lead.send_lead()

            # Insert a note with the response and payload
            note = frappe.get_doc(
                {
                    "doctype": "Note",
                    "title": "Lead Created in Facebook Successfully",
                    "public": 1,
                    "content": (
                        "Lead Created in Facebook Successfully <br> Response: "
                        + str(response)
                        + "<br> Payload: "
                        + json.dumps(f_payload, indent=2)
                    ),
                    "custom_reference_name": lead.name,
                }
            )
            note.insert(ignore_permissions=True)


@frappe.whitelist()
def trigger_fetch_leads(name):
    fetch = FetchLeads(name)
    fetch.fetch_leads()
    return {"form_ids": fetch.form_ids}


@frappe.whitelist()
def regenerate_map_lead_fields(name):
    """Rebuild `map_lead_fields` for an existing Sync New Add doc using the
    currently-stored Meta forms (`table_hsya`), without re-calling Meta API.

    This also auto-creates any missing Custom Fields on the Lead doctype.
    """
    doc = frappe.get_doc("Sync New Add", name)
    # Clear existing rows
    doc.set("map_lead_fields", [])
    form_fields = []
    appender = AppendForms(lead_forms=None, doc=doc)
    for lead_form_row in doc.table_hsya:
        questions_val = lead_form_row.questions
        if isinstance(questions_val, str):
            questions = json.loads(questions_val).get("questions")
        else:
            questions = (questions_val or {}).get("questions")
        if not questions:
            continue
        appender.set_map_lead_fields(questions, form_fields)
    # Persist without calling the Meta API again.
    doc.flags.skip_meta_fetch = True
    doc.save(ignore_permissions=True)
    return {"rows": len(doc.map_lead_fields)}


class SyncNewAdd(Document):
    def after_insert(self):
        if getattr(self, "fetch_map_lead_fields", 0) and getattr(self, "table_hsya", None):
            regenerate_map_lead_fields(self.name)

    def validate(self):
        if getattr(self.flags, "skip_meta_fetch", False):
            return
        defaults = get_credentials()
        #  init Request
        request = Request(
            defaults.api_url,
            defaults.graph_api_version,
            self.page_id,
            None,
            params={
                "fields": "access_token",
                "transport": "cors",
                "access_token": defaults.access_token,
            },
        )
        # init RequestPageAccessToken
        request_page_access_token = RequestPageAccessToken(request)
        # get page access token
        request_page_access_token.get_page_access_token()
        # init Request
        request = Request(
            defaults.api_url,
            defaults.graph_api_version,
            self.page_id + f"/leadgen_forms",
            None,
            params={
                "access_token": request_page_access_token.page_access_token,
                "fields": "name,id,created_time,leads_count,page,page_id,\
         questions,leads {\
            ad_id,campaign_id,adset_id,campaign_name,ad_name,form_id,id,\
                adset_name,created_time\
                    }",
            },
        )
        # init RequestLeadGenFroms
        request_lead_gen_forms = RequestLeadGenFroms(request)
        # get lead forms
        request_lead_gen_forms.get_lead_forms()
        # init AppendForms
        append_forms = AppendForms(request_lead_gen_forms.lead_forms, self)
        # append forms
        append_forms.append_forms()

    def check_email_id(self):
        first_name = False
        for row in self.map_lead_fields:
            if row.lead_field == "first_name":
                first_name = True
        if not first_name:
            frappe.throw("Please map First Name Field")

    def check_meta_fields_found(self):
        if frappe.get_meta(self.lead_doctype_name).has_field("custom_meta_lead_id"):
            pass
        else:
            # create custom fields
            frappe.get_doc(
                {
                    "doctype": "Custom Field",
                    "dt": "Lead",
                    "fieldname": "custom_meta_lead_id",
                    "label": "Custom Meta Lead ID",
                    "fieldtype": "Data",
                    "insert_after": "name",
                    "read_only": 1,
                }
            ).insert(ignore_permissions=True)
        if frappe.get_meta(self.lead_doctype_name).has_field("custom_lead_json"):
            pass
        else:
            # create custom fields
            frappe.get_doc(
                {
                    "doctype": "Custom Field",
                    "dt": "Lead",
                    "fieldname": "custom_lead_json",
                    "label": "Custom Lead JSON",
                    "fieldtype": "Text",
                    "insert_after": "custom_meta_lead_id",
                    "read_only": 1,
                }
            ).insert(ignore_permissions=True)

    def on_submit(self):
        self.check_meta_fields_found()
        self.check_email_id()
        server_script = ServerScript(self)
        server_script.create_server_script()
        server_script.server_script.insert(ignore_permissions=True)
        frappe.db.commit()
        frappe.msgprint("Server Script Created Successfully")

    def on_cancel(self):
        script_name = str(self.name).lower().replace("-", "_")
        if frappe.db.exists("Server Script", script_name):
            frappe.delete_doc("Server Script", script_name, ignore_permissions=True)
            frappe.msgprint("Server Script Deleted Successfully")
