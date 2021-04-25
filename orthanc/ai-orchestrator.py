import orthanc,pprint,json,datetime,random,sys

#TODO store things into the DB
#TODO set a timer to automatically expire workitems after a given amount of time?

###############################################################################
# GLOBALS
###############################################################################
WORKITEMS = dict()
DICOM_UID_ROOT = '2.7446.76257' # 2.SIIM.ROCKS
STATE_SCHEDULED = "SCHEDULED"
STATE_IN_PROGRESS = "IN PROGRESS"
STATE_COMPLETED = "COMPLETED"
STATE_CANCELED = "CANCELED"
STATES = [STATE_SCHEDULED, STATE_CANCELED, STATE_COMPLETED, STATE_IN_PROGRESS]
REQUIRED_TAGS = ['00080016','00080018','00081195','00081199','00100010','00100020','00100030','00100040','0020000D','00404041','0040A370','0040E025','00404005','00741000','00741200','00741204']

###############################################################################
# ORTHANC EVENT HOOKS
###############################################################################
# List all work
def listOrCreateWorkitems(output, uri, **request):
    if request['method'] == 'GET':
        #TODO Add support for filtering via a GET query
        output.AnswerBuffer(json.dumps(list(WORKITEMS.values())), 'application/dicom+json')

    if request['method'] == 'POST':
        try:
            workitem = json.loads(request['body'])
            missingAttributes = checkRequiredTagsPresent(workitem)

            # Check this new object has the bare-minimum tags/attributes
            if len(missingAttributes) > 0:
                msg = "Your new object is missing the following attribute(s): " + ", ".join(missingAttributes)
                output.SendHttpStatus(400, msg, len(msg))
                return

            # Check this study is NOT already listed
            if checkStudyUIDExists(workitem['0020000D']['Value'][0]):
                msg = "This study is already listed as a workitem"
                output.SendHttpStatus(400, msg, len(msg))
                return

            # If all successfull so far, store the item
            workitemId = getDicomIdentifier()
            WORKITEMS[workitemId] = workitem
            output.AnswerBuffer(json.dumps(WORKITEMS[workitemId]), 'application/dicom+json')

        except:
            errorInfo = sys.exc_info()
            msg = "Unknown error occurred, might be caused by invalid data input. Error message was: " + errorInfo[0]
            print("Unhandled error while attempting to create a workitem manually: " + errorInfo[0])
            print(errorInfo[2])
            output.SendHttpStatus(500, msg, len(msg))
            return

    else:
        output.SendMethodNotAllowed('GET,POST')
        return

orthanc.RegisterRestCallback('/ai-orchestrator/workitems', listOrCreateWorkitems)

def getWorkitem(output, uri, **request):
    if request['method'] != 'GET':
        output.SendMethodNotAllowed('GET')
        return

    workitemId = request['groups'][0]
    if (workitemId not in WORKITEMS):
        msg = "No workitem found matching the ID supplied: " + workitemId
        output.SendHttpStatus(404, msg, len(msg))
        return
    output.AnswerBuffer(json.dumps(WORKITEMS[workitemId]), 'application/dicom+json')

orthanc.RegisterRestCallback('/ai-orchestrator/workitems/([0-9\\.]*)', getWorkitem)


def changeWorkItemState(output, uri, **request):
    if request['method'] != 'PUT':
        output.SendMethodNotAllowed('PUT')
        return

    workitemId = request['groups'][0]
    if (workitemId not in WORKITEMS):
        msg = "No workitem found matching the ID supplied: " + workitemId
        output.SendHttpStatus(404, msg, len(msg))
        return
    # Check the integrity of the new object
    new = json.loads(request['body'])
    old = WORKITEMS[workitemId]
    missingAttributes = checkRequiredTagsPresent(new)

    # Check this new object has the bare-minimum tags/attributes
    if len(missingAttributes) > 0:
        msg = "Your new object is missing the following attribute(s): " + ", ".join(missingAttributes)
        output.SendHttpStatus(400, msg, len(msg))
        return

    # Next check, the status should be one of the known statuses
    if new['00741000']['Value'][0] not in STATES:
        msg = "Your object's ProcedureStepState (00741000) must be one of: " + ", ".join(STATES)
        output.SendHttpStatus(400, msg, len(msg))
        return

    # Check the correct succession of states (scheduled -> in progress (OR canceled) -> completed OR canceled)
    oldState = old['00741000']['Value'][0]
    newState = new['00741000']['Value'][0]
    if oldState == STATE_SCHEDULED and (newState != STATE_IN_PROGRESS and newState != STATE_CANCELED):
        msg = "A workitem that is currently in SCHEDULED state can only move to IN PROGRESS or CANCELED"
        output.SendHttpStatus(400, msg, len(msg))
        return
    if oldState == STATE_IN_PROGRESS and (newState != STATE_COMPLETED and newState != STATE_CANCELED):
        msg = "A workitem that is currently in IN PROGRESS state can only move to COMPLETED or CANCELED"
        output.SendHttpStatus(400, msg, len(msg))
        return

    # If successful - store the new object
    WORKITEMS[workitemId] = new
    output.AnswerBuffer(json.dumps(WORKITEMS[workitemId]), 'application/dicom+json')

orthanc.RegisterRestCallback('/ai-orchestrator/workitems/([0-9\\.]*)/state', changeWorkItemState)


def OnChange(changeType, level, resourceId):
    if changeType == orthanc.ChangeType.ORTHANC_STARTED: # Server start-up
        print('AI-orchestrator plugin running!')

    if changeType == orthanc.ChangeType.STABLE_STUDY: # Study has stopped receiving news instances/series
        print('Stable study: %s' % resourceId)

        # Get more information about this study
        study = json.loads(orthanc.RestApiGet('/studies/' + resourceId))
        studyUid = study['MainDicomTags']['StudyInstanceUID']
        series = []
        bodyPart = None
        modality = None

        # Check this study is NOT already listed
        if checkStudyUIDExists(studyUid):
            print("This study is already listed as a workitem")
            return

        # Loop through the series within this study, and get additional attributes for each
        for seriesId in study['Series']:
            data = json.loads(orthanc.RestApiGet('/series/' + seriesId + '/shared-tags'))
            series.append(data)
            if( bodyPart == None ):
                bodyPart = str(data['0018,0015']['Value'])
                modality = str(data['0008,0060']['Value'])

        # TODO improve this to be more dynamic
        pipline = bodyPart.lower() + '-' + modality.lower() + '-pipeline'

        # Create a workitem for this study
        workitemId = getDicomIdentifier()
        workitem = {
            '00080016': {'vr':'UI', 'Value': ['1.2.840.10008.5.1.4.34.6.1']}, # SOPClassUID
            '00080018': {'vr':'UI', 'Value': [workitemId]}, # SOPInstanceUID
            '00081195': {'vr':'UI', 'Value': ['']}, # UI [] TransactionUID
            '00081199': {'vr':'SQ', 'Value': [
                # This repeats for every series within the target study, so it is handled in a loop below
            ]}, # ReferencedSOPSequence
            '00100010': {'vr':'PN', 'Value': [study['PatientMainDicomTags']['PatientName']]}, # PatientName
            '00100020': {'vr':'LO', 'Value': [study['PatientMainDicomTags']['PatientID']]}, # PatientID
            '00100030': {'vr':'DA', 'Value': [study['PatientMainDicomTags']['PatientBirthDate']]}, # PatientBirthDate
            '00100040': {'vr':'CS', 'Value': [study['PatientMainDicomTags']['PatientSex']]}, # PatientSex
            '0020000D': {'vr':'UI', 'Value': [studyUid]}, # Study Instance UID
            '00404041': {'vr':'CS', 'Value': ['READY']}, # InputReadinessState
            '0040A370': {'vr':'SQ', 'Value': [{
                '00080050': {'vr': 'UI', 'Value': [study['MainDicomTags']['AccessionNumber']]}, #AccessionNumber
                '0020000D': {'vr': 'UI', 'Value': [studyUid]},  # Study Instance UID
            }]}, # SQ ReferencedRequestSequence
            '0040E025': {'vr':'SQ', 'Value': [{
                '00081190': {'vr': 'LO', 'Value': ['http://localhost:8042/dicom-web/studies/' + studyUid]}, # Retrieve URL
            }]}, # WADORSRetrievalSequence
            '00404005': {'vr':'DT', 'Value': [getDicomDate()]}, # Scheduled Procedure Step Start DateTime
            '00741000': {'vr':'CS', 'Value': [STATE_SCHEDULED]}, # ProcedureStepState
            '00741200': {'vr':'CS', 'Value': ['MEDIUM']}, # ScheduledProcedureStepPriority
            '00741204': {'vr':'LO', 'Value': [pipline]}, # ProcedureStepLabel

        }
        for curSeries in series:
            workitem['00081199']['Value'].append({
                '00081150': {'vr': 'UI', 'Value': [curSeries['0008,0016']['Value']]},  # ReferencedSOPClassUID
                '00081155': {'vr': 'UI', 'Value': [curSeries['0020,000e']['Value']]},  # ReferencedSeriesUID
            })
        WORKITEMS[workitemId] = workitem
        #pprint.pprint(workitem)

orthanc.RegisterOnChangeCallback(OnChange)


###############################################################################
# UTILITY METHODS
###############################################################################
# Create a random DICOM UID
def getDicomIdentifier():
    uid = DICOM_UID_ROOT
    parts = random.randint(3,6)
    i = 0
    while i < parts:
        uid += '.' + str(random.randint(1,999999999))
        i += 1
    return uid

# Return DICOM-formatted date. If not date provided, it defaults to now
def getDicomDate(date=None):
    if( date == None ):
        date = datetime.datetime.now()
    return date.strftime('%Y%m%d%H%M%S')

# Check a given study is NOT already listed
def checkStudyUIDExists(studyUid):
    for workitem in WORKITEMS.values():
        if studyUid == workitem['0020000D']['Value'][0]:
            return True
    return False

# Check a new/update workitem object to have the bare-minimum attributes
def checkRequiredTagsPresent(workitem):
    missingAttributes = []
    for key in REQUIRED_TAGS:
        if key not in workitem:
            missingAttributes.append(key)
    return missingAttributes