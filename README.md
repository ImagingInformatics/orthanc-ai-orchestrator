# AI Wokflow Orchestrator
Orthanc Plugin to simulate an AI Workflow Orchestrator (maintaining workitem tickets/jobs
for AI pipeline "workitems"). This is an example implementation for demonstration
purposes only at this point. It may evolve into a more mature product over time, 
but right now, it is 100% work in progress.

---

# Usage
## Starting up 
After cloning this repository, run the following command to start the Orthanc docker
with this plugin running:

`sudo docker-compose up --build`

Afterwards, upload one or more studies into Orthanc. After **5 seconds** (the configured
waiting period for a "stable" study), you can perform an HTTP GET to:

`http://localhost:8042/ai-orchestrator/workitems`

Which should return a list of workitems (same number as the number of studies you uploaded).
The workitems are [DICOM JSON objects](https://www.dicomstandard.org/dicomweb/dicom-json-format).

## Workitem Manipulation

### Get an individual workitem
Perform an HTTP GET to

`http://localhost:8042/ai-orchestrator/workitems/xxx`

Replace `xxx` with the workitem's ID that you got from the listing.

### Changing a workitem's state
Perform an HTTP PUT to

`http://localhost:8042/ai-orchestrator/workitems/xxx/state`

Replace `xxx` with the workitem's ID that you got from the listing. The body of your 
request should be identical to work item you are trying adjust, except for the 
00741000 attribute (aka Procedure Step State). Which should have one of the following
values:
* SCHEDULED
* IN PROGRESS
* CANCELED
* COMPLETED

---
# Credits
* [Brad Genereaux](https://twitter.com/IntegratorBrad) - The mastermind behind the idea
  and developer of the first, Java-based, proof-of-concept 
* [Mohannad Hussain](https://github.com/mohannadhussain) - Developed this iteration of
  the AI Orchestrator as an Orthanc Python Plugin
* [Society for Imaging Informatics in Medicine (SIIM)](https://siim.org) - For fostering
  innovation in Imaging IT/Informatics and sponsoring this project
---
# Contribution
* Code: Fork this repository, make your changes, then submit a poll request.
* Other: Contact [Mohannad Hussain](https://github.com/mohannadhussain) 