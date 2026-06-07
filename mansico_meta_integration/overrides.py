import frappe
from frappe.utils.scheduler import is_scheduler_disabled
from frappe import _
from mansico_meta_integration.mansico_meta_integration.doctype.sync_new_add.sync_new_add import FetchLeads

def validate_lead(doc, method=None):
    _validate_lead_status_change(doc, "Lead")

def validate_crmlead(doc, method=None):
    _validate_lead_status_change(doc, "CRM Lead")

def _validate_lead_status_change(doc, doctype):
    """
    Helper function to validate status change and trigger Facebook lead creation.
    """
    if not doc.is_new() and doc.custom_meta_lead_id:
        old_doc = doc.get_doc_before_save()
        if old_doc and old_doc.status != doc.status:
            if is_scheduler_disabled():
                frappe.throw(_("Please enable the Scheduler first."))
            try:
                lead = frappe.get_doc(doctype, doc.name)
                FetchLeads.create_lead_in_facebook(lead)
            except Exception as e:
                frappe.log_error(
                    title=f"Error in {doctype} Facebook Lead Creation",
                    message=f"An error occurred while creating a Facebook lead for {doctype} {doc.name}: {str(e)}"
                )