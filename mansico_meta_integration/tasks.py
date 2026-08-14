

import frappe
from mansico_meta_integration.mansico_meta_integration.doctype.sync_new_add.sync_new_add import FetchLeads


def _run(event_frequency):
    sync_new_add = frappe.db.get_all("Sync New Add", {"event_frequency": event_frequency, "docstatus": 1}, pluck="name")
    for name in sync_new_add:
        fetch = FetchLeads(name)
        fetch.fetch_leads()


@frappe.whitelist()
def fetch_all_leads():
    _run("All")

@frappe.whitelist()
def fetch_daily_leads():
    _run("Daily")

@frappe.whitelist()
def fetch_hourly_leads():
    _run("Hourly")

@frappe.whitelist()
def fetch_weekly_leads():
    _run("Weekly")

@frappe.whitelist()
def fetch_monthly_leads():
    _run("Monthly")
