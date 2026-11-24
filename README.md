# Prospecting Automation

Three Python scripts that turn public business listings into structured records for prospect research and CRM import review.

| Source format | Python code | Output |
| --- | --- | --- |
| Expandable directory | [Accordion directory parser](accordion_directory.py) | Organization names and locations, with missing cities flagged for review |
| Plain-text listings | [Text listings parser](stockists_to_close.py) | CRM-shaped CSV and a separate review file |
| Location map | [Store locator parser](retailer_locator.py) | Unique locations, an organization rollup, and a missing-information report |

[Download the complete project](Prospecting-Automation.zip) for the example inputs, expected outputs, run instructions, tests, and a visual overview. The scripts run locally on Python 3.9+ and require no third-party packages.

The code is based on real projects I developed. Example records are fictional to protect client confidentiality. This portfolio version reads local files only; it does not connect to live websites or a CRM.

[Back to Systems Portfolio](https://aaatanasi.github.io/crm-systems-portfolio/#prospect-title)
