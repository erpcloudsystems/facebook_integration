import json

import frappe
from mansico_meta_integration.mansico_meta_integration.doctype.sync_new_add.sync_new_add import (
    FetchLeads,
)


def validate_lead(doc, method=None):
    _enqueue_lead_status_change(doc, "Lead")


def validate_crmlead(doc, method=None):
    _enqueue_lead_status_change(doc, "CRM Lead")


def _enqueue_lead_status_change(doc, doctype):
    """On a status change of a Meta-sourced lead, push the new status to
    Facebook as a conversion event.

    The actual Facebook API call runs in a background job (enqueued only
    *after* the document is successfully committed), so a slow or failing
    request never blocks the user's save. This replaces the old behaviour that
    hard-`throw`-ed when the scheduler was disabled and called Facebook
    synchronously inside `validate`.
    """
    if doc.is_new() or not doc.custom_meta_lead_id:
        return

    old_doc = doc.get_doc_before_save()
    if not old_doc or old_doc.status == doc.status:
        return

    frappe.enqueue(
        "mansico_meta_integration.overrides.send_lead_status_to_facebook",
        queue="short",
        enqueue_after_commit=True,
        doctype=doctype,
        name=doc.name,
        status=doc.status,
    )


def send_lead_status_to_facebook(doctype, name, status=None):
    """Background job: send the lead's current status to Facebook (Meta CAPI)."""
    try:
        lead = frappe.get_doc(doctype, name)
        page = _get_page_for_lead(lead)
        if not page:
            frappe.log_error(
                title=f"Meta CAPI: no Page ID for {doctype} {name}",
                message=(
                    f"Could not resolve a Page ID (pixel) for {doctype} {name}; "
                    f"status '{status}' was not sent to Facebook."
                ),
            )
            return
        FetchLeads.create_lead_in_facebook(lead, page)
    except Exception:
        frappe.log_error(
            title=f"Error sending {doctype} status to Facebook",
            message=frappe.get_traceback(),
        )


def _get_page_for_lead(lead):
    """Resolve the `Page ID` doc (which holds the pixel id + access token) for a
    Meta-sourced lead.

    Strategy:
      1. Use the lead's originating Facebook form (`form_id` stored in
         `custom_lead_json`) to find the owning `Sync New Add`, then its page.
      2. Fall back to the only configured `Page ID` if there is exactly one.
    """
    page_name = None

    form_id = _get_form_id(lead)
    if form_id:
        sync_name = frappe.db.get_value(
            "Meta Forms",
            {"form_id": form_id, "parenttype": "Sync New Add"},
            "parent",
        )
        if sync_name:
            page_name = frappe.db.get_value("Sync New Add", sync_name, "page_id")

    if not page_name:
        pages = frappe.get_all("Page ID", pluck="name", limit=2)
        if len(pages) == 1:
            page_name = pages[0]

    return frappe.get_doc("Page ID", page_name) if page_name else None


def _get_form_id(lead):
    """Extract the originating Facebook `form_id` from the lead's stored JSON."""
    raw = lead.get("custom_lead_json")
    if not raw:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return None
    return data.get("form_id") if isinstance(data, dict) else None
