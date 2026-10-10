// Homeowners create, list and read their own jobs.
permit (
  principal in Group::"Homeowner",
  action in [Action::"CreateJob", Action::"ListJobs", Action::"ReadJob"],
  resource
)
when { resource.owner == principal };

// Installers can also batch-create and export, still only on their own data.
permit (
  principal in Group::"Installer",
  action in [Action::"CreateJob", Action::"ListJobs", Action::"ReadJob", Action::"BatchCreate", Action::"ExportCsv"],
  resource
)
when { resource.owner == principal };

// Batch is installer-only, even if a future permit is written too broadly.
forbid (principal, action == Action::"BatchCreate", resource)
unless { principal in Group::"Installer" };
