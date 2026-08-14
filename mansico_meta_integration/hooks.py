app_name = "mansico_meta_integration"
app_title = "Mansico Meta Integration"
app_publisher = "Mansy"
app_description = "This project is about syncing Facebook leads with ERPnext, When Clients fill Facebook ads instant forms app automatic fetch new created leads and create lead automatic in Lead doctype. Also on changing the Lead Status the new status sent to meta Pixel."
app_email = "ahmedmansy265@gmail.com"
app_license = "mit"
required_apps = ["erpnext"]

doc_events = {
    "Lead": {
        # will run before a ToDo record is inserted into database
        "validate": "mansico_meta_integration.overrides.validate_lead",
    }
}


doc_events["CRM Lead"] = {
        "validate": "mansico_meta_integration.overrides.validate_crmlead",
    }
# Scheduled Tasks
# ---------------

scheduler_events = {
	"all": [
		"mansico_meta_integration.tasks.fetch_all_leads"
	],
	"daily": [
		"mansico_meta_integration.tasks.fetch_daily_leads"
	],
	"hourly": [
		"mansico_meta_integration.tasks.fetch_hourly_leads"
	],
	"weekly": [
		"mansico_meta_integration.tasks.fetch_weekly_leads"
	],
	"monthly": [
		"mansico_meta_integration.tasks.fetch_monthly_leads"
	],
}
