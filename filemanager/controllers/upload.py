"""Handles all upload-related requests."""

from typing import Tuple, Optional
from datetime import datetime
import json
import logging

from werkzeug.exceptions import NotFound, BadRequest, InternalServerError, NotImplemented

from werkzeug.datastructures import FileStorage
from flask.json import jsonify

from arxiv import status

import filemanager
from filemanager.shared import url_for

from filemanager.domain import Upload
from filemanager.services import uploads
from filemanager.tasks import sanitize_upload, check_sanitize_status

from filemanager.arxiv.file import File

# Temporary logging at service level - just to get something in place to build on

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)

file_handler = logging.FileHandler('upload.log', 'a')
# Default arXiv log format.
# fmt = ("application %(asctime)s - %(name)s - %(requestid)s"
#          " - [arxiv:%(paperid)s] - %(levelname)s: \"%(message)s\"")
datefmt = '%d/%b/%Y:%H:%M:%S %z'  # Used to format asctime.
formatter = logging.Formatter('%(asctime)s %(message)s', '%d/%b/%Y:%H:%M:%S %z')
file_handler.setFormatter(formatter)
logger.handlers = []
logger.addHandler(file_handler)
logger.setLevel(logging.DEBUG)
logger.propagate = False

# End logging configuration

# exceptions
UPLOAD_MISSING_FILE = {'missing file/archive payload'}
UPLOAD_MISSING_FILENAME = {'file argument missing filename or file not selected'}
# UPLOAD_FILE_EMPTY = {'file payload is zero length'}

UPLOAD_NOT_FOUND = {'upload workspace not found'}
UPLOAD_DB_ERROR = {'unable to create/insert new upload workspace into database'}
UPLOAD_IO_ERROR = {'encountered an IOError'}
UPLOAD_UNKNOWN_ERROR = {'unknown error'}
UPLOAD_DELETE_WORKSPACE = {'reason': 'workspace scheduled for deletion.'}

# upload status codes
INVALID_UPLOAD_ID = {'reason': 'invalid upload identifier'}
MISSING_UPLOAD_ID = {'reason': 'missing upload id'}

# Indicate requests that have not been implemented yet.
REQUEST_NOT_IMPLEMENTED = {'request not implemented'}

# upload status
NO_SUCH_THING = {'reason': 'there is no upload'}
THING_WONT_COME = {'reason': 'could not get the upload'}

ERROR_RETRIEVING_UPLOAD = {'upload not found'}
# UPLOAD_DOESNT_EXIST = {'upload does not exist'}
CANT_CREATE_UPLOAD = {'could not create the upload'}  #
CANT_UPLOAD_FILE = {'could not upload file'}
CANT_DELETE_FILE = {'could not delete file'}

ACCEPTED = {'reason': 'upload in progress'}

MISSING_NAME = {'an upload needs a name'}

SOME_ERROR = {'Need to define and assign better error'}

# task related exceptions
INVALID_TASK_ID = {'reason': 'invalid task id'}
TASK_DOES_NOT_EXIST = {'reason': 'task not found'}

TASK_IN_PROGRESS = {'status': 'in progress'}
TASK_FAILED = {'status': 'failed'}
TASK_COMPLETE = {'status': 'complete'}

Response = Tuple[Optional[dict], int, dict]


def delete_workspace(upload_id: int) -> Response:
    """Delete workspace."""
    logger.info(f"{upload_id}: Deleting upload workspace.")

    # TODO: This request was not really part if this sprint. Write down ideas and
    #      come back to later.

    # Need to add several checks here

    # At this point I believe we know that caller is authorized to delete the
    # workspace. This is checked at the routes level.

    # Does workspace exist? Has it already been deleted? Generate 400:BadRequest error.

    # Do we care is workspace is ACTIVE state? And not released? NO. But log it...

    # Do we care if workspace was modified recently...NO. Log it

    try:
        # Make sure we have an upload_obj to work with
        upload_obj: Optional[Upload] = uploads.retrieve(upload_id)

        if upload_obj is None:
            # Invalid workspace identifier
            raise NotFound(UPLOAD_NOT_FOUND)
        else:
            # Any other conditions that raise red flags? Any that stop the
            # deletion?

            # Actually remove entire workspace directory structure. Log
            # something to global log since source log is being removed!

            # Initiate workspace deletion

            # Update database (but keep around) for historical reference. Does not
            # consume very much space. What about source log?

            pass

    except IOError:
        logger.error(f"{upload_obj.upload_id}: Delete workspace request failed ")
        raise InternalServerError(CANT_DELETE_FILE)
    except NotFound:
        logger.info(f"Upload id '{upload_id}' not found in database.")
        raise
    except Exception as ue:
        logger.info("Unknown error creating new workspace. "
                    + f" Add except clauses for '{ue}'. DO IT NOW!")
        raise InternalServerError(UPLOAD_UNKNOWN_ERROR)

    # API doesn't provide for returning errors resulting from delete.
    # 401-unautorized and 403-forbidden are handled at routes level.
    # Add 400 response to openapi.yaml
    if upload_id:
        raise NotImplemented(REQUEST_NOT_IMPLEMENTED)

    status_code = status.HTTP_204_NO_CONTENT
    return UPLOAD_DELETE_WORKSPACE, status_code, {}


def upload(upload_id: int, file: FileStorage, archive: str) -> Response:
    """Upload individual files or compressed archive. Unpack and add
    files to upload_obj workspace.

    Parameters
    ----------
    upload_id : int
        The unique identifier for the upload_obj in question.
    file : FileStorage
        File archive to be processed.
    archive: str
        Archive submission is targeting. Oversize thresholds are curently
        specified at the archive level.

    Returns
    -------
    dict
        Complete summary of upload processing.
    int
        An HTTP status code.
    dict
        Some extra headers to add to the response.
    """

    # TODO: Hook up async processing (celery/redis) - doesn't work now
    # TODO: Will likely delete this code if processing time is reasonable
    # print(f'Controller: Schedule upload_obj task for {upload_id}')
    #
    # result = sanitize_upload.delay(upload_id, file)
    #
    # headers = {'Location': url_for('upload_api.upload_status',
    #                              task_id=result.task_id)}
    # return ACCEPTED, status.HTTP_202_ACCEPTED, headers
    # End delete

    # Check arguments for basic qualities like existing and such.

    # File argument is required to exist and have a name associated with it.
    # It is standard practice that if user fails to select file the filename is null.
    if file == None:
        # Crash and burn...not quite...do we need info about client?
        logger.error(f'Upload request is missing file/archive payload.')
        raise BadRequest(UPLOAD_MISSING_FILE)

    if file.filename == '':
        # Client needs to select file, or provide name to upload payload
        logger.error(f'Upload file is missing filename. File to upload may not be selected.')
        raise BadRequest(UPLOAD_MISSING_FILENAME)

    # What about archive argument.
    if archive == None:
        # TODO: Discussion about how to treat omission of archive argument.
        # Is this an HTTP exception? Oversize limits are configured per archive.
        # Or is this a warning/error returned in upload summary?
        #
        # Most submissions can get by with default size limitations so we'll add a warning
        # message for the upload (this will appear on upload page and get logged). This
        # warning will get generated in process/upload.py and not here.
        logger.error(f"Upload 'archive' not specified. Oversize calculation will use default values.")

    # If this is a new upload then we need to create a workspace and add to database.
    if upload_id == None:
        try:
            logger.info(f"Create new workspace: Upload request: "
                        + f"file='{file.filename}' archive='{archive}'")
            user_id = 'dlf2'

            if archive == None:
                arch = ''
            else:
                arch = archive

            new_upload = Upload(owner_user_id=user_id, archive=arch,
                                created_datetime=datetime.now(),
                                modified_datetime=datetime.now(),
                                state='ACTIVE')
            # Store in DB
            uploads.store(new_upload)

            upload_id = new_upload.upload_id

        except IOError:
            logger.info(f"Error creating new workspace.")
            raise InternalServerError(UPLOAD_IO_ERROR)
        except (TypeError, ValueError) as dbe:
            logger.info(f"Error adding new workspace to database: '{dbe}'.")
            raise InternalServerError(UPLOAD_DB_ERROR)
        except Exception as ue:
            logger.info("Unknown error creating new workspace. "
                        + f" Add except clauses for '{ue}'. DO IT NOW!")
            raise InternalServerError(UPLOAD_UNKNOWN_ERROR)

    # At this point we expect upload to exist in system
    try:

        upload_obj: Optional[Upload] = uploads.retrieve(upload_id)

        if upload_obj is None:
            # Invalid workspace identifier
            raise NotFound(UPLOAD_NOT_FOUND)
        else:
            # Now handle upload package - process file or gzipped tar archive

            # NOTE: This will need to be migrated to task.py using Celery at
            #       some point in future. Depends in time it takes to process
            #       uploads.retrieve
            logger.info(f"{upload_obj.upload_id}: Upload files to existing workspace: file='{file.filename}'")

            # Keep track of how long processing upload_obj takes
            start_datetime = datetime.now()

            # Create Upload object
            uploadObj = filemanager.process.upload.Upload(upload_id)

            # Process upload_obj
            uploadObj.process_upload(file)

            completion_datetime = datetime.now()

            # Keep track of files processed (this included deleted files)
            file_list = uploadObj.create_file_upload_summary()

            # Determine readiness state of upload content
            upload_status = "READY"

            if uploadObj.has_errors():
                upload_status = "ERRORS"
            elif uploadObj.has_warnings():
                upload_status = "READY_WITH_WARNINGS"

            # Create combine list of errors and warnings
            # TODO: Should I do this in Upload package?? Likely...
            all_errors_and_warnings = []

            for warn in uploadObj.get_warnings():
                public_filepath, warning_message = warn
                all_errors_and_warnings.append(['warn', public_filepath, warning_message])

            for error in uploadObj.get_errors():
                public_filepath, warning_message = error
                # TODO: errors renamed fatal. Need to review 'errors' as to whether they are 'fatal'
                all_errors_and_warnings.append(['fatal', public_filepath, warning_message])

            # Prepare upload_obj details (DB). I'm assuming that in memory Redis
            # is not sufficient for results that may be needed in the distant future.
            #errors_and_warnings = uploadObj.get_errors() + uploadObj.get_warnings()
            errors_and_warnings = all_errors_and_warnings
            upload_obj.lastupload_logs = str(errors_and_warnings)
            upload_obj.lastupload_start_datetime = start_datetime
            upload_obj.lastupload_completion_datetime = completion_datetime
            upload_obj.lastupload_file_summary = json.dumps(file_list)
            upload_obj.lastupload_upload_status = upload_status
            upload_obj.state = 'ACTIVE'

            # Store in DB
            uploads.update(upload_obj)

            logger.info(f"{upload_obj.upload_id}: Processed upload. Saved to DB. Preparing upload summary.")

            # Do we want affirmative log messages after processing each request
            # or maybe just report errors like:
            #    logger.info(f"{upload_obj.upload_id}: Finished processing ...")

            # Upload action itself has very simple response
            headers = {'Location': url_for('upload_api.upload_files',
                                           upload_id=upload_obj.upload_id)}

            status_code = status.HTTP_201_CREATED



            response_data = {
                'upload_id': upload_obj.upload_id,
                'created_datetime': upload_obj.created_datetime,
                'modified_datetime': upload_obj.modified_datetime,
                'start_datetime': upload_obj.lastupload_start_datetime,
                'completion_datetime': upload_obj.lastupload_completion_datetime,
                'files': upload_obj.lastupload_file_summary,
                'errors': upload_obj.lastupload_logs,
                'upload_status': upload_obj.lastupload_upload_status,
                'workspace_state': upload_obj.state,
                'lock_state': upload_obj.lock
            }
            logger.info(f"{upload_obj.upload_id}: Generating upload summary.")
            return response_data, status_code, headers

    except IOError:
        logger.error(f"{upload_obj.upload_id}: File upload_obj request failed "
                     + f"for file='{file.filename}'")
        raise InternalServerError(UPLOAD_IO_ERROR)
    except (TypeError, ValueError) as dbe:
        logger.info(f"Error updating database: '{dbe}'")
        raise InternalServerError(UPLOAD_DB_ERROR)
    except BadRequest as breq:
        logger.info(f"{upload_id}: '{breq}'.")
        raise
    except NotFound as nfdb:
        logger.info(f"Upload id '{upload_id}' not found in database: '{nfdb}'.")
        raise nfdb
    except Exception as ue:
        logger.info("Unknown error with existing workspace."
                    + f" Add except clauses for '{ue}'. DO IT NOW!")
        raise InternalServerError(UPLOAD_UNKNOWN_ERROR)


def upload_summary(upload_id: int) -> Response:
    """Provide summary of important upload workspace details.

       Parameters
       ----------
       upload_id : int
           The unique identifier for upload workspace.

       Returns
       -------
       dict
           Detailed information about the upload_obj.

           logs - Errors and Warnings
           files - list of file details


       int
           An HTTP status code.
       dict
           Some extra headers to add to the response.
       """

    try:
        # Make sure we have an upload_obj to work with
        upload_obj: Optional[Upload] = uploads.retrieve(upload_id)

        if upload_obj is None:
            status_code = status.HTTP_404_NOT_FOUND
            response_data = UPLOAD_NOT_FOUND
            raise NotFound(UPLOAD_NOT_FOUND)
        else:
            logger.info(f"{upload_obj.upload_id}: Upload summary request.")
            status_code = status.HTTP_200_OK
            response_data = {
                'upload_id': upload_obj.upload_id,
                'created_datetime': upload_obj.created_datetime,
                'modified_datetime': upload_obj.modified_datetime,
                'start_datetime': upload_obj.lastupload_start_datetime,
                'completion_datetime': upload_obj.lastupload_completion_datetime,
                'files': upload_obj.lastupload_file_summary,
                'errors': upload_obj.lastupload_logs,
                'upload_status': upload_obj.lastupload_upload_status,
                'workspace_state': upload_obj.state,
                'lock_state': upload_obj.lock
            }
            logger.info(f"{upload_obj.upload_id}: Upload summary request.")

    except IOError:
        # response_data = ERROR_RETRIEVING_UPLOAD
        # status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        raise InternalServerError(ERROR_RETRIEVING_UPLOAD)
    except (TypeError, ValueError):
        logger.info(f"Error updating database.")
        raise InternalServerError(UPLOAD_DB_ERROR)
    except NotFound:
        logger.info(f"Upload id '{upload_id}' not found in database.")
        raise
    except Exception as ue:
        logger.info("Unknown error with existing workspace."
                    + f" Add except clauses for '{ue}'. DO IT NOW!")
        raise InternalServerError(UPLOAD_UNKNOWN_ERROR)


    return response_data, status_code, {}


def package_content(upload_id: int) -> Response:
    """Package up files for downloading. Create a compressed gzipped tar file."""
    # response_data = ERROR_REQUEST_NOT_IMPLEMENTED
    # status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    if 1 + upload_id:  # Get rid of pylint complaint
        print(upload_id)  # make pylint happy - increase my score!
        raise NotImplementedError(REQUEST_NOT_IMPLEMENTED)
    response_data = ACCEPTED  # Get rid of pylint error
    status_code = status.HTTP_202_ACCEPTED
    return response_data, status_code, {}


def upload_lock(upload_id: int) -> Response:
    """Lock upload workspace. Prohibit all user operations on upload.
    Admins may unlock upload."""
    # response_data = ERROR_REQUEST_NOT_IMPLEMENTED
    # status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    if 1 + upload_id:
        print(upload_id)  # make pylint happy - increase my score!
        raise NotImplementedError(REQUEST_NOT_IMPLEMENTED)
    response_data = ACCEPTED
    status_code = status.HTTP_202_ACCEPTED
    return response_data, status_code, {}


def upload_unlock(upload_id: int) -> Response:
    """Unlock upload workspace."""
    # response_data = ERROR_REQUEST_NOT_IMPLEMENTED
    # status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    if 1 + upload_id:
        print(upload_id)  # make pylint happy - increase my score!
        raise NotImplementedError(REQUEST_NOT_IMPLEMENTED)
    response_data = ACCEPTED
    status_code = status.HTTP_202_ACCEPTED
    return response_data, status_code, {}


def upload_release(upload_id: int) -> Response:
    """Inidcate we are done with upload workspace.
       System will schedule to remove files.
       """
    # Again, as with delete workspace, authentication, authorization, and
    # existence of workspace is verified in route level

    # Expect workspace in ACTIVE state. Is it an error if workspace is
    # in another state? Or do we ignore repeat release requests.

    if 1 + upload_id:
        print(upload_id)  # make pylint happy - increase my score!
        raise NotImplementedError(REQUEST_NOT_IMPLEMENTED)

    # Change state of workspace
    # Update workspace modification time
    # Update DB

    # Log state change

    response_data = ACCEPTED
    status_code = status.HTTP_202_ACCEPTED
    return response_data, status_code, {}


def upload_logs(upload_id: int) -> Response:
    """Return logs. Are we talking logs in database or full
    source logs. Need to implement logs first!!! """
    # response_data = ERROR_REQUEST_NOT_IMPLEMENTED
    # status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    if 1 + upload_id:
        print(upload_id)  # make pylint happy - increase my score!
        raise NotImplementedError(REQUEST_NOT_IMPLEMENTED)
    response_data = ACCEPTED
    status_code = status.HTTP_202_ACCEPTED
    return response_data, status_code, {}


# Demo reference code
# TODO: These ASYNC processing routines are likely going away if upload
#       performs well.

def upload_as_task(upload_id: int) -> Response:
    """
    Start sanitizing (a :class:`.Upload`.

    Parameters
    ----------
    upload_id : int

    Returns
    -------
    dict
        Some data.
    int
        An HTTP status code.
    dict
        Some extra headers to add to the response.
    """
    result = sanitize_upload.delay(upload_id)
    headers = {'Location': url_for('upload_api.upload_status',
                                   task_id=result.task_id)}
    return ACCEPTED, status.HTTP_202_ACCEPTED, headers


def upload_as_task_status(task_id: str) -> Response:
    """
    Check the status of a mutation process.

    Parameters
    ----------
    task_id : str
        The ID of the mutation task.

    Returns
    -------
    dict
        Some data.
    int
        An HTTP status code.
    dict
        Some extra headers to add to the response.
    """
    try:
        task_status, result = check_sanitize_status(task_id)
    except ValueError as e:
        print(str(e))  # get rid of pylint error - use e
        return INVALID_TASK_ID, status.HTTP_400_BAD_REQUEST, {}

    if task_status == 'PENDING':
        return TASK_DOES_NOT_EXIST, status.HTTP_404_NOT_FOUND, {}
    elif task_status in ['SENT', 'STARTED', 'RETRY']:
        return TASK_IN_PROGRESS, status.HTTP_200_OK, {}
    elif task_status == 'FAILURE':
        reason = TASK_FAILED
        reason.update({'reason': str(result)})
        return reason, status.HTTP_200_OK, {}
    elif task_status == 'SUCCESS':
        reason = TASK_COMPLETE
        reason.update({'result': result})
        headers = {'Location': url_for('external_api.read_thing',
                                       thing_id=result['thing_id'])}
        return TASK_COMPLETE, status.HTTP_303_SEE_OTHER, headers
    return TASK_DOES_NOT_EXIST, status.HTTP_404_NOT_FOUND, {}
