// Copyright (c) 2023, mansy and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sync New Add", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}
		frm.add_custom_button("Regenerate Map Lead Fields", () => {
			frappe.call({
				method:
					"mansico_meta_integration.mansico_meta_integration.doctype.sync_new_add.sync_new_add.regenerate_map_lead_fields",
				args: { name: frm.doc.name },
				freeze: true,
				callback: () => {
					frappe.msgprint("Map Lead Fields regenerated successfully");
					frm.reload_doc();
				},
			});
		});
	},
});
