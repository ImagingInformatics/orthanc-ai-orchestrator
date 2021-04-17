import orthanc,pprint,json,datetime,random

#TODO store things into the DB?
#TODO check that the study is not already listed as a workitem when adding a new one
#TODO set a timer to automatically expire workitems after a given amount of time?
#TODO Add method checks to enfore GET vs. POST vs. PUT

###############################################################################
# GLOBALS
###############################################################################
WORKITEMS = dict()
DICOM_UID_ROOT = '2.7446.76257' # 2.SIIM.ROCKS
STATE_SCHEDULED = "SCHEDULED"
STATE_IN_PROGRESS = "IN PROGRESS"
STATE_COMPLETED = "COMPLETED"
STATE_CANCELED = "CANCELED"


###############################################################################
# ORTHANC EVENT HOOKS
###############################################################################
# List all work
#TODO Add support for filtering via a GET query
def listWorkitems(output, uri, **request):
    output.AnswerBuffer(json.dumps(list(WORKITEMS.values())), 'application/dicom+json')

orthanc.RegisterRestCallback('/ai-orchestrator/workitems', listWorkitems)

def getWorkitem(output, uri, **request):
    workitemId = request['groups'][0]
    if (workitemId not in WORKITEMS):
        print('aaaaaaaaaaaaaaaa')
        msg = "No workitem found matching the ID supplied: " + workitemId
        output.SendHttpStatus(404, msg, len(msg))
        return
    output.AnswerBuffer(json.dumps(WORKITEMS[workitemId]), 'application/dicom+json')

orthanc.RegisterRestCallback('/ai-orchestrator/workitems/([0-9\\.]*)', getWorkitem)


def changeWorkItemState(output, uri, **request):
    workitemId = request['groups'][0]
    if (workitemId not in WORKITEMS):
        print('bbbbbbbbbbbbbbbb')
        msg = "No workitem found matching the ID supplied: " + workitemId
        output.SendHttpStatus(404, msg, len(msg))
        return
    print(request['body'])
    WORKITEMS[workitemId] = json.loads(request['body'])
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

        # Loop through the series within this study, and get additional attributes for each
        for seriesId in study['Series']:
            data = json.loads(orthanc.RestApiGet('/series/' + seriesId + '/shared-tags'))
            series.append(data)
            if( bodyPart == None ):
                bodyPart = str(data['0018,0015']['Value'])
                modality = str(data['0008,0060']['Value'])
        pipline = bodyPart.lower() + '-' + modality.lower() + '-pipeline' # TODO improve this to be more dynamic

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
        pprint.pprint(workitem)

orthanc.RegisterOnChangeCallback(OnChange)


###############################################################################
# UTILITY METHODS
###############################################################################
def getDicomIdentifier():
    uid = DICOM_UID_ROOT
    parts = random.randint(3,6)
    i = 0
    while i < parts:
        uid += '.' + str(random.randint(1,999999999))
        i += 1
    return uid

def getDicomDate(date=None):
    if( date == None ):
        date = datetime.datetime.now()
    return date.strftime('%Y%m%d%H%M%S')

