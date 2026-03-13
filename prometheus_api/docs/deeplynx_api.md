v1

OAS 3.1.1

# DeepLynx Nexus API

[Nexus Documentation](https://deeplynx.inl.gov/docs)

[Nexus Support](mailto:Jaren.Brownlee@inl.gov)

Download OpenAPI Document

json

Download OpenAPI Document

yaml

DeepLynx Nexus API for managing organizational data and relationships.
Endpoints are organized by Organization-level
(/api/organizations/{organizationId}) and Project-level
(/api/projects/{projectId}) scopes.

Server

Server:https://deeplynx.inl.gov/api/v1

##

AuthenticationOptional

Select Auth Type

No authentication selected

Client Libraries

Shell

Ruby

Node.js

PHP

Python

More Select from all clients

Shell Curl

## Organization  (Collapsed)

​Copy link

Organization management

Organization Operations

  * get/organizations
  * post/organizations
  * get/organizations/user
  * get/organizations/{organizationId}
  * put/organizations/{organizationId}
  * delete/organizations/{organizationId}
  * patch/organizations/{organizationId}
  * post/organizations/{organizationId}/user
  * delete/organizations/{organizationId}/user
  * put/organizations/{organizationId}/admin
  * post/organizations/{organizationId}/invite

Show More

## Project  (Collapsed)

​Copy link

Project management

Project Operations

  * get/organizations/{organizationId}/projects
  * post/organizations/{organizationId}/projects
  * get/organizations/{organizationId}/projects/GetProjectsByUser
  * get/organizations/{organizationId}/projects/{projectId}
  * put/organizations/{organizationId}/projects/{projectId}
  * delete/organizations/{organizationId}/projects/{projectId}
  * patch/organizations/{organizationId}/projects/{projectId}
  * get/organizations/{organizationId}/projects/{projectId}/stats
  * get/organizations/{organizationId}/projects/{projectId}/members
  * post/organizations/{organizationId}/projects/{projectId}/members
  * put/organizations/{organizationId}/projects/{projectId}/members
  * delete/organizations/{organizationId}/projects/{projectId}/members
  * post/organizations/{organizationId}/projects/{projectId}/invite

Show More

## User  (Collapsed)

​Copy link

User management

User Operations

  * get/users
  * post/users
  * get/users/{userId}
  * put/users/{userId}
  * delete/users/{userId}
  * patch/users/{userId}
  * get/users/superuser
  * patch/users/{userId}/admin
  * get/users/{userId}/overview
  * get/users/current

Show More

## Group  (Collapsed)

​Copy link

Group management

Group Operations

  * get/organizations/{organizationId}/groups
  * post/organizations/{organizationId}/groups
  * get/organizations/{organizationId}/groups/{groupId}
  * put/organizations/{organizationId}/groups/{groupId}
  * delete/organizations/{organizationId}/groups/{groupId}
  * patch/organizations/{organizationId}/groups/{groupId}
  * get/organizations/{organizationId}/groups/{groupId}/users
  * post/organizations/{organizationId}/groups/{groupId}/users
  * delete/organizations/{organizationId}/groups/{groupId}/users/{userId}

Show More

## OauthHandshake  (Collapsed)

​Copy link

OAuth2 authorization flow

OauthHandshake Operations

  * get/oauth/authorize
  * post/oauth/exchange

Show More

## Token  (Collapsed)

​Copy link

API key and JWT token management

Token Operations

  * post/oauth/tokens
  * post/oauth/keys
  * get/oauth/keys
  * delete/oauth/keys/{key}
  * delete/oauth/tokens/revoke

Show More

## OauthApplication  (Collapsed)

​Copy link

OAuth apps

OauthApplication Operations

  * get/oauth/applications
  * post/oauth/applications
  * get/oauth/applications/{applicationId}
  * put/oauth/applications/{applicationId}
  * delete/oauth/applications/{applicationId}
  * patch/oauth/applications/{applicationId}

Show More

## Organization - Class  (Collapsed)

​Copy link

Organization-level class operations

Organization - Class Operations

  * get/organizations/{organizationId}/classes
  * post/organizations/{organizationId}/classes
  * get/organizations/{organizationId}/classes/{classId}
  * put/organizations/{organizationId}/classes/{classId}
  * delete/organizations/{organizationId}/classes/{classId}
  * patch/organizations/{organizationId}/classes/{classId}
  * post/organizations/{organizationId}/classes/bulk

Show More

## Project - Class  (Collapsed)

​Copy link

Project-level class operations

Project - Class Operations

  * get/projects/{projectId}/classes
  * post/projects/{projectId}/classes
  * get/projects/{projectId}/classes/{classId}
  * put/projects/{projectId}/classes/{classId}
  * delete/projects/{projectId}/classes/{classId}
  * patch/projects/{projectId}/classes/{classId}
  * post/projects/{projectId}/classes/bulk

Show More

## Record  (Collapsed)

​Copy link

Record management

Record Operations

  * get/organizations/{organizationId}/projects/{projectId}/records
  * post/organizations/{organizationId}/projects/{projectId}/records
  * get/organizations/{organizationId}/projects/{projectId}/records/by-tags
  * get/organizations/{organizationId}/projects/{projectId}/records/{recordId}
  * put/organizations/{organizationId}/projects/{projectId}/records/{recordId}
  * delete/organizations/{organizationId}/projects/{projectId}/records/{recordId}
  * patch/organizations/{organizationId}/projects/{projectId}/records/{recordId}
  * get/organizations/{organizationId}/projects/{projectId}/records/count
  * post/organizations/{organizationId}/projects/{projectId}/records/bulk
  * post/organizations/{organizationId}/projects/{projectId}/records/{recordId}/tags
  * delete/organizations/{organizationId}/projects/{projectId}/records/{recordId}/tags
  * get/organizations/{organizationId}/projects/{projectId}/records/{recordId}/edges
  * get/organizations/{organizationId}/projects/{projectId}/records/{recordId}/graph

Show More

## Historical Record  (Collapsed)

​Copy link

Record history

Historical Record Operations

  * get/organizations/{organizationId}/projects/{projectId}/records/historical
  * get/organizations/{organizationId}/projects/{projectId}/records/historical/{recordId}
  * get/organizations/{organizationId}/projects/{projectId}/records/historical/{recordId}/history

Show More

## Edge  (Collapsed)

​Copy link

Edges

Edge Operations

  * get/organizations/{organizationId}/projects/{projectId}/edges
  * post/organizations/{organizationId}/projects/{projectId}/edges
  * get/organizations/{organizationId}/projects/{projectId}/edges/{edgeId}
  * put/organizations/{organizationId}/projects/{projectId}/edges/{edgeId}
  * delete/organizations/{organizationId}/projects/{projectId}/edges/{edgeId}
  * patch/organizations/{organizationId}/projects/{projectId}/edges/{edgeId}
  * get/organizations/{organizationId}/projects/{projectId}/edges/by-relationship
  * put/organizations/{organizationId}/projects/{projectId}/edges/by-relationship
  * delete/organizations/{organizationId}/projects/{projectId}/edges/by-relationship
  * patch/organizations/{organizationId}/projects/{projectId}/edges/by-relationship
  * post/organizations/{organizationId}/projects/{projectId}/edges/bulk

Show More

## Historical Edge  (Collapsed)

​Copy link

Edge history

Historical Edge Operations

  * get/organizations/{organizationId}/projects/{projectId}/edges/historical
  * get/organizations/{organizationId}/projects/{projectId}/edges/historical/{edgeId}
  * get/organizations/{organizationId}/projects/{projectId}/edges/historical/by-relationship
  * get/organizations/{organizationId}/projects/{projectId}/edges/historical/{edgeId}/history
  * get/organizations/{organizationId}/projects/{projectId}/edges/historical/by-relationship/history

Show More

## File  (Collapsed)

​Copy link

File operations

File Operations

  * post/organizations/{organizationId}/projects/{projectId}/files
  * put/organizations/{organizationId}/projects/{projectId}/files/{recordId}
  * get/organizations/{organizationId}/projects/{projectId}/files/{recordId}
  * delete/organizations/{organizationId}/projects/{projectId}/files/{recordId}
  * post/organizations/{organizationId}/projects/{projectId}/files/upload/start
  * post/organizations/{organizationId}/projects/{projectId}/files/upload/chunk
  * post/organizations/{organizationId}/projects/{projectId}/files/upload/complete
  * delete/organizations/{organizationId}/projects/{projectId}/files/upload/{uploadId}

Show More

## Metadata  (Collapsed)

​Copy link

Metadata operations

Metadata Operations

  * post/organizations/{organizationId}/projects/{projectId}/datasources/{dataSourceId}/metadata
  * post/organizations/{organizationId}/projects/{projectId}/datasources/{dataSourceId}/metadata/file

Show More

## Organization - DataSource  (Collapsed)

​Copy link

Organization-level data sources

Organization - DataSource Operations

  * get/organizations/{organizationId}/datasources
  * post/organizations/{organizationId}/datasources
  * get/organizations/{organizationId}/datasources/{dataSourceId}
  * put/organizations/{organizationId}/datasources/{dataSourceId}
  * delete/organizations/{organizationId}/datasources/{dataSourceId}
  * patch/organizations/{organizationId}/datasources/{dataSourceId}
  * get/organizations/{organizationId}/datasources/default
  * patch/organizations/{organizationId}/datasources/{dataSourceId}/default

Show More

## Project - DataSource  (Collapsed)

​Copy link

Project-level data sources

Project - DataSource Operations

  * get/projects/{projectId}/datasources
  * post/projects/{projectId}/datasources
  * get/projects/{projectId}/datasources/{dataSourceId}
  * put/projects/{projectId}/datasources/{dataSourceId}
  * delete/projects/{projectId}/datasources/{dataSourceId}
  * patch/projects/{projectId}/datasources/{dataSourceId}
  * get/projects/{projectId}/datasources/default
  * patch/projects/{projectId}/datasources/{dataSourceId}/default

Show More

## Event  (Collapsed)

​Copy link

Event logs

Event Operations

  * get/events/GetAllEvents
  * get/events/QueryEvents
  * get/events/QueryAuthorizedEvents/{organizationId}
  * get/events/QueryEventsBySubscriptions

### Get All Events

​Copy link

Query Parameters

  * projectIdCopy link to projectId

Type: integer | string` Pattern:  ^-?(?:0|[1-9]\d*)$`Format: int64

Optional filter to only include events matching the projectId

  * organizationIdCopy link to organizationId

Type: integer | string` Pattern:  ^-?(?:0|[1-9]\d*)$`Format: int64

Optional filter

Responses

  * 200

Selected Content Type:text/plain

  * 401Copy link to 401

Unauthorized - Invalid or missing authentication token

  * 403Copy link to 403

Forbidden - Insufficient permissions

  * 500Copy link to 500

Internal Server Error

Request Example for get/events/GetAllEvents

Shell Curl

    
    
    curl 'https://deeplynx.inl.gov/api/v1/events/GetAllEvents?projectId=1&organizationId=1'
    

Test Request(get /events/GetAllEvents)

Status: 200Status: 401Status: 403Status: 500

Show Schema

    
    
    {
      "items": [
        {
          "id": 1,
          "operation": "string",
          "entityType": "string",
          "entityId": null,
          "projectId": null,
          "organizationId": null,
          "organizationName": "string",
          "dataSourceId": null,
          "properties": "string",
          "projectName": null,
          "entityName": null,
          "dataSourceName": null,
          "lastUpdatedAt": "2026-02-10T18:44:53.109Z",
          "lastUpdatedBy": null,
          "lastUpdatedByUserName": null
        }
      ],
      "pageNumber": 1,
      "pageSize": 1,
      "totalCount": 1,
      "totalPages": 1,
      "hasPrevious": true,
      "hasNext": true
    }

### QueryEvents (Paginated)

​Copy link

Query Parameters

  * organizationIdCopy link to organizationId

Type: integer | string` Pattern:  ^-?(?:0|[1-9]\d*)$`Format: int64

The id of the organization

  * projectIdCopy link to projectId

Type: integer | string` Pattern:  ^-?(?:0|[1-9]\d*)$`Format: int64

The id of the project

  * LastUpdatedByCopy link to LastUpdatedBy

Type: integer | string` Pattern:  ^-?(?:0|[1-9]\d*)$`Format: int64

  * ProjectNameCopy link to ProjectName

Type: string

  * OperationCopy link to Operation

Type: string

  * EntityTypeCopy link to EntityType

Type: string

  * EntityNameCopy link to EntityName

Type: string

  * DataSourceNameCopy link to DataSourceName

Type: string

  * StartDateCopy link to StartDate

Type: stringFormat: date-time

the date-time notation as defined by RFC 3339, section 5.6, for example,
2017-07-21T17:32:28Z

  * EndDateCopy link to EndDate

Type: stringFormat: date-time

the date-time notation as defined by RFC 3339, section 5.6, for example,
2017-07-21T17:32:28Z

  * PageNumberCopy link to PageNumber

Type: integer | string` Pattern:  ^-?(?:0|[1-9]\d*)$`Format: int32

  * PageSizeCopy link to PageSize

Type: integer | string` Pattern:  ^-?(?:0|[1-9]\d*)$`Format: int32

Responses

  * 200

Selected Content Type:text/plain

  * 401Copy link to 401

Unauthorized - Invalid or missing authentication token

  * 403Copy link to 403

Forbidden - Insufficient permissions

  * 500Copy link to 500

Internal Server Error

Request Example for get/events/QueryEvents

Shell Curl

    
    
    curl 'https://deeplynx.inl.gov/api/v1/events/QueryEvents?organizationId=1&projectId=1&LastUpdatedBy=1&ProjectName=&Operation=&EntityType=&EntityName=&DataSourceName=&StartDate=&EndDate=&PageNumber=1&PageSize=1'
    

Test Request(get /events/QueryEvents)

Status: 200Status: 401Status: 403Status: 500

Show Schema

    
    
    {
      "items": [
        {
          "id": 1,
          "operation": "string",
          "entityType": "string",
          "entityId": null,
          "projectId": null,
          "organizationId": null,
          "organizationName": "string",
          "dataSourceId": null,
          "properties": "string",
          "projectName": null,
          "entityName": null,
          "dataSourceName": null,
          "lastUpdatedAt": "2026-02-10T18:44:53.109Z",
          "lastUpdatedBy": null,
          "lastUpdatedByUserName": null
        }
      ],
      "pageNumber": 1,
      "pageSize": 1,
      "totalCount": 1,
      "totalPages": 1,
      "hasPrevious": true,
      "hasNext": true
    }

### Query All Events The requesting user is Authorized to See (Paginated).

​Copy link

Path Parameters

  * organizationIdCopy link to organizationId

Type: integerFormat: int64

required

Signed 64-bit integers (long type).

Query Parameters

  * projectIdsCopy link to projectIds

Type: array integer | string[]

  * LastUpdatedByCopy link to LastUpdatedBy

Type: integer | string` Pattern:  ^-?(?:0|[1-9]\d*)$`Format: int64

  * ProjectNameCopy link to ProjectName

Type: string

  * OperationCopy link to Operation

Type: string

  * EntityTypeCopy link to EntityType

Type: string

  * EntityNameCopy link to EntityName

Type: string

  * DataSourceNameCopy link to DataSourceName

Type: string

  * StartDateCopy link to StartDate

Type: stringFormat: date-time

the date-time notation as defined by RFC 3339, section 5.6, for example,
2017-07-21T17:32:28Z

  * EndDateCopy link to EndDate

Type: stringFormat: date-time

the date-time notation as defined by RFC 3339, section 5.6, for example,
2017-07-21T17:32:28Z

  * PageNumberCopy link to PageNumber

Type: integer | string` Pattern:  ^-?(?:0|[1-9]\d*)$`Format: int32

  * PageSizeCopy link to PageSize

Type: integer | string` Pattern:  ^-?(?:0|[1-9]\d*)$`Format: int32

Responses

  * 200

OK

Selected Content Type:text/plain

  * 401Copy link to 401

Unauthorized - Invalid or missing authentication token

  * 403Copy link to 403

Forbidden - Insufficient permissions

  * 500Copy link to 500

Internal Server Error

Request Example for get/events/QueryAuthorizedEvents/_{organizationId}_

Shell Curl

    
    
    curl 'https://deeplynx.inl.gov/api/v1/events/QueryAuthorizedEvents/1?projectIds=1&LastUpdatedBy=1&ProjectName=&Operation=&EntityType=&EntityName=&DataSourceName=&StartDate=&EndDate=&PageNumber=1&PageSize=1'
    

Test Request(get /events/QueryAuthorizedEvents/{organizationId})

Status: 200Status: 401Status: 403Status: 500

Show Schema

    
    
    [
      {
        "id": 1,
        "operation": "string",
        "entityType": "string",
        "entityId": null,
        "projectId": null,
        "organizationId": null,
        "organizationName": "string",
        "dataSourceId": null,
        "properties": "string",
        "projectName": null,
        "entityName": null,
        "dataSourceName": null,
        "lastUpdatedAt": "2026-02-10T18:44:53.109Z",
        "lastUpdatedBy": null,
        "lastUpdatedByUserName": null
      }
    ]

OK

### Query Events by Subscriptions

​Copy link

Query Parameters

  * organizationIdCopy link to organizationId

Type: integer | string` Pattern:  ^-?(?:0|[1-9]\d*)$`Format: int64

The ID of the organization

  * projectIdCopy link to projectId

Type: integer | string` Pattern:  ^-?(?:0|[1-9]\d*)$`Format: int64

The ID of the project to which the events belong

  * LastUpdatedByCopy link to LastUpdatedBy

Type: integer | string` Pattern:  ^-?(?:0|[1-9]\d*)$`Format: int64

  * ProjectNameCopy link to ProjectName

Type: string

  * OperationCopy link to Operation

Type: string

  * EntityTypeCopy link to EntityType

Type: string

  * EntityNameCopy link to EntityName

Type: string

  * DataSourceNameCopy link to DataSourceName

Type: string

  * StartDateCopy link to StartDate

Type: stringFormat: date-time

the date-time notation as defined by RFC 3339, section 5.6, for example,
2017-07-21T17:32:28Z

  * EndDateCopy link to EndDate

Type: stringFormat: date-time

the date-time notation as defined by RFC 3339, section 5.6, for example,
2017-07-21T17:32:28Z

  * PageNumberCopy link to PageNumber

Type: integer | string` Pattern:  ^-?(?:0|[1-9]\d*)$`Format: int32

  * PageSizeCopy link to PageSize

Type: integer | string` Pattern:  ^-?(?:0|[1-9]\d*)$`Format: int32

Responses

  * 200

Selected Content Type:text/plain

  * 401Copy link to 401

Unauthorized - Invalid or missing authentication token

  * 403Copy link to 403

Forbidden - Insufficient permissions

  * 500Copy link to 500

Internal Server Error

Request Example for get/events/QueryEventsBySubscriptions

Shell Curl

    
    
    curl 'https://deeplynx.inl.gov/api/v1/events/QueryEventsBySubscriptions?organizationId=1&projectId=1&LastUpdatedBy=1&ProjectName=&Operation=&EntityType=&EntityName=&DataSourceName=&StartDate=&EndDate=&PageNumber=1&PageSize=1'
    

Test Request(get /events/QueryEventsBySubscriptions)

Status: 200Status: 401Status: 403Status: 500

Show Schema

    
    
    [
      {
        "id": 1,
        "operation": "string",
        "entityType": "string",
        "entityId": null,
        "projectId": null,
        "organizationId": null,
        "organizationName": "string",
        "dataSourceId": null,
        "properties": "string",
        "projectName": null,
        "entityName": null,
        "dataSourceName": null,
        "lastUpdatedAt": "2026-02-10T18:44:53.109Z",
        "lastUpdatedBy": null,
        "lastUpdatedByUserName": null
      }
    ]

## Organization - Object Storage  (Collapsed)

​Copy link

Organization-level storage

Organization - Object Storage Operations

  * get/organizations/{organizationId}/storages
  * post/organizations/{organizationId}/storages
  * get/organizations/{organizationId}/storages/{objectStorageId}
  * put/organizations/{organizationId}/storages/{objectStorageId}
  * delete/organizations/{organizationId}/storages/{objectStorageId}
  * patch/organizations/{organizationId}/storages/{objectStorageId}
  * get/organizations/{organizationId}/storages/default
  * patch/organizations/{organizationId}/storages/{objectStorageId}/default

Show More

## Project - Object Storage  (Collapsed)

​Copy link

Project-level storage

Project - Object Storage Operations

  * get/organizations/{organizationId}/projects/{projectId}/storages
  * post/organizations/{organizationId}/projects/{projectId}/storages
  * get/organizations/{organizationId}/projects/{projectId}/storages/{objectStorageId}
  * put/organizations/{organizationId}/projects/{projectId}/storages/{objectStorageId}
  * delete/organizations/{organizationId}/projects/{projectId}/storages/{objectStorageId}
  * patch/organizations/{organizationId}/projects/{projectId}/storages/{objectStorageId}
  * get/organizations/{organizationId}/projects/{projectId}/storages/default
  * patch/organizations/{organizationId}/projects/{projectId}/storages/{objectStorageId}/default

Show More

## Organization - Permission  (Collapsed)

​Copy link

Organization-level permissions

Organization - Permission Operations

  * get/organizations/{organizationId}/permissions
  * post/organizations/{organizationId}/permissions
  * get/organizations/{organizationId}/permissions/{permissionId}
  * put/organizations/{organizationId}/permissions/{permissionId}
  * delete/organizations/{organizationId}/permissions/{permissionId}
  * patch/organizations/{organizationId}/permissions/{permissionId}

Show More

## Project - Permission  (Collapsed)

​Copy link

Project-level permissions

Project - Permission Operations

  * get/organizations/{organizationId}/projects/{projectId}/permissions
  * post/organizations/{organizationId}/projects/{projectId}/permissions
  * get/organizations/{organizationId}/projects/{projectId}/permissions/{permissionId}
  * put/organizations/{organizationId}/projects/{projectId}/permissions/{permissionId}
  * delete/organizations/{organizationId}/projects/{projectId}/permissions/{permissionId}
  * patch/organizations/{organizationId}/projects/{projectId}/permissions/{permissionId}

Show More

## Query  (Collapsed)

​Copy link

Search and filtering

Query Operations

  * get/organizations/{organizationId}/query/records
  * post/organizations/{organizationId}/query/records/advanced
  * get/organizations/{organizationId}/query/recent
  * get/organizations/{organizationId}/query/multiproject

Show More

## Saved Search  (Collapsed)

​Copy link

Saved searches

Saved Search Operations

  * post/saved-searches
  * get/saved-searches

Show More

## Organization - Relationship  (Collapsed)

​Copy link

Organization-level relationships

Organization - Relationship Operations

  * get/organizations/{organizationId}/relationships
  * post/organizations/{organizationId}/relationships
  * get/organizations/{organizationId}/relationships/{relationshipId}
  * put/organizations/{organizationId}/relationships/{relationshipId}
  * delete/organizations/{organizationId}/relationships/{relationshipId}
  * patch/organizations/{organizationId}/relationships/{relationshipId}
  * post/organizations/{organizationId}/relationships/bulk

Show More

## Project - Relationship  (Collapsed)

​Copy link

Project-level relationships

Project - Relationship Operations

  * get/projects/{projectId}/relationships
  * post/projects/{projectId}/relationships
  * get/projects/{projectId}/relationships/{relationshipId}
  * put/projects/{projectId}/relationships/{relationshipId}
  * delete/projects/{projectId}/relationships/{relationshipId}
  * patch/projects/{projectId}/relationships/{relationshipId}
  * post/projects/{projectId}/relationships/bulk

Show More

## Organization - Role  (Collapsed)

​Copy link

Organization-level roles

Organization - Role Operations

  * get/organizations/{organizationId}/roles
  * post/organizations/{organizationId}/roles
  * get/organizations/{organizationId}/roles/{roleId}
  * put/organizations/{organizationId}/roles/{roleId}
  * delete/organizations/{organizationId}/roles/{roleId}
  * patch/organizations/{organizationId}/roles/{roleId}
  * get/organizations/{organizationId}/roles/{roleId}/permissions
  * put/organizations/{organizationId}/roles/{roleId}/permissions
  * post/organizations/{organizationId}/roles/{roleId}/permissions/{permissionId}
  * delete/organizations/{organizationId}/roles/{roleId}/permissions/{permissionId}

Show More

## Project - Role  (Collapsed)

​Copy link

Project-level roles

Project - Role Operations

  * get/organizations/{organizationId}/projects/{projectId}/roles
  * post/organizations/{organizationId}/projects/{projectId}/roles
  * get/organizations/{organizationId}/projects/{projectId}/roles/{roleId}
  * put/organizations/{organizationId}/projects/{projectId}/roles/{roleId}
  * delete/organizations/{organizationId}/projects/{projectId}/roles/{roleId}
  * patch/organizations/{organizationId}/projects/{projectId}/roles/{roleId}
  * get/organizations/{organizationId}/projects/{projectId}/roles/{roleId}/permissions
  * put/organizations/{organizationId}/projects/{projectId}/roles/{roleId}/permissions
  * post/organizations/{organizationId}/projects/{projectId}/roles/{roleId}/permissions/{permissionId}
  * delete/organizations/{organizationId}/projects/{projectId}/roles/{roleId}/permissions/{permissionId}

Show More

## Organization - Sensitivity Label  (Collapsed)

​Copy link

Organization-level labels

Organization - Sensitivity Label Operations

  * get/organizations/{organizationId}/labels
  * post/organizations/{organizationId}/labels
  * get/organizations/{organizationId}/labels/{labelId}
  * put/organizations/{organizationId}/labels/{labelId}
  * delete/organizations/{organizationId}/labels/{labelId}
  * patch/organizations/{organizationId}/labels/{labelId}

Show More

## Project - Sensitivity Label  (Collapsed)

​Copy link

Project-level labels

Project - Sensitivity Label Operations

  * get/projects/{projectId}/labels
  * post/projects/{projectId}/labels
  * get/projects/{projectId}/labels/{labelId}
  * put/projects/{projectId}/labels/{labelId}
  * delete/projects/{projectId}/labels/{labelId}
  * patch/projects/{projectId}/labels/{labelId}

Show More

## Organization - Tag  (Collapsed)

​Copy link

Organization-level tags

Organization - Tag Operations

  * get/organizations/{organizationId}/tags
  * post/organizations/{organizationId}/tags
  * get/organizations/{organizationId}/tags/{tagId}
  * put/organizations/{organizationId}/tags/{tagId}
  * delete/organizations/{organizationId}/tags/{tagId}
  * patch/organizations/{organizationId}/tags/{tagId}
  * post/organizations/{organizationId}/tags/bulk

Show More

## Project - Tag  (Collapsed)

​Copy link

Project-level tags

Project - Tag Operations

  * get/projects/{projectId}/tags
  * post/projects/{projectId}/tags
  * get/projects/{projectId}/tags/{tagId}
  * put/projects/{projectId}/tags/{tagId}
  * delete/projects/{projectId}/tags/{tagId}
  * patch/projects/{projectId}/tags/{tagId}
  * post/projects/{projectId}/tags/bulk

Show More

## Timeseries  (Collapsed)

​Copy link

Time-series data

Timeseries Operations

  * post/organizations/{organizationId}/projects/{projectId}/datasources/{dataSourceId}/timeseries/query
  * post/organizations/{organizationId}/projects/{projectId}/datasources/{dataSourceId}/timeseries/upload
  * post/organizations/{organizationId}/projects/{projectId}/datasources/{dataSourceId}/timeseries/upload/start
  * post/organizations/{organizationId}/projects/{projectId}/datasources/{dataSourceId}/timeseries/upload/chunk
  * post/organizations/{organizationId}/projects/{projectId}/datasources/{dataSourceId}/timeseries/upload/complete
  * patch/organizations/{organizationId}/projects/{projectId}/datasources/{dataSourceId}/timeseries/append
  * get/organizations/{organizationId}/projects/{projectId}/datasources/{dataSourceId}/timeseries/interpolate
  * get/organizations/{organizationId}/projects/{projectId}/datasources/{dataSourceId}/timeseries/export

### Query Timeseries

​Copy link

Path Parameters

  * organizationIdCopy link to organizationId

Type: integerFormat: int64

required

ID of organization that timeseries data is associated with

  * projectIdCopy link to projectId

Type: integerFormat: int64

required

ID of project that timeseries data is associated with

  * dataSourceIdCopy link to dataSourceId

Type: integerFormat: int64

required

ID of data source that timeseries data is associated with

Query Parameters

  * fileTypeCopy link to fileType

Type: string

The type of file to convert query to

Body

required

Selected Content Type:application/json

The request containing an sql query string

  * queryCopy link to query

Type: string

required

Responses

  * 200

Selected Content Type:text/plain

  * 401Copy link to 401

Unauthorized - Invalid or missing authentication token

  * 403Copy link to 403

Forbidden - Insufficient permissions

  * 500Copy link to 500

Internal Server Error

Request Example for post/organizations/_{organizationId}_
/projects/_{projectId}_ /datasources/_{dataSourceId}_ /timeseries/query

Shell Curl

    
    
    curl 'https://deeplynx.inl.gov/api/v1/organizations/1/projects/1/datasources/1/timeseries/query?fileType=' \
      --request POST \
      --header 'Content-Type: application/json' \
      --data '{
      "query": ""
    }'
    

Test Request(post
/organizations/{organizationId}/projects/{projectId}/datasources/{dataSourceId}/timeseries/query)

Status: 200Status: 401Status: 403Status: 500

Show Schema

    
    
    {
      "id": 1,
      "name": "string",
      "description": "string",
      "uri": null,
      "properties": "string",
      "objectStorageId": null,
      "originalId": "string",
      "classId": null,
      "dataSourceId": 1,
      "projectId": 1,
      "organizationId": 1,
      "lastUpdatedAt": "2026-02-10T18:44:53.109Z",
      "lastUpdatedBy": null,
      "isArchived": true,
      "fileType": null,
      "tags": [
        {
          "id": 1,
          "name": "string"
        }
      ]
    }

### Upload Timeseries File

​Copy link

Path Parameters

  * organizationIdCopy link to organizationId

Type: integerFormat: int64

required

ID of organization that timeseries data is associated with

  * projectIdCopy link to projectId

Type: integerFormat: int64

required

ID of project that timeseries data is associated with

  * dataSourceIdCopy link to dataSourceId

Type: integerFormat: int64

required

ID of data source that timeseries data is associated with

Body

required

multipart/form-data

Timeseries file

  * fileCopy link to file

Type: stringFormat: binary

binary data, used to describe files

Responses

  * 200

Record response DTO

Selected Content Type:text/plain

  * 401Copy link to 401

Unauthorized - Invalid or missing authentication token

  * 403Copy link to 403

Forbidden - Insufficient permissions

  * 500Copy link to 500

Internal Server Error

Request Example for post/organizations/_{organizationId}_
/projects/_{projectId}_ /datasources/_{dataSourceId}_ /timeseries/upload

Shell Curl

    
    
    curl https://deeplynx.inl.gov/api/v1/organizations/1/projects/1/datasources/1/timeseries/upload \
      --request POST \
      --header 'Content-Type: multipart/form-data'
    

Test Request(post
/organizations/{organizationId}/projects/{projectId}/datasources/{dataSourceId}/timeseries/upload)

Status: 200Status: 401Status: 403Status: 500

Show Schema

    
    
    {
      "id": 1,
      "name": "string",
      "description": "string",
      "uri": null,
      "properties": "string",
      "objectStorageId": null,
      "originalId": "string",
      "classId": null,
      "dataSourceId": 1,
      "projectId": 1,
      "organizationId": 1,
      "lastUpdatedAt": "2026-02-10T18:44:53.109Z",
      "lastUpdatedBy": null,
      "isArchived": true,
      "fileType": null,
      "tags": [
        {
          "id": 1,
          "name": "string"
        }
      ]
    }

Record response DTO

### Start Timeseries Upload

​Copy link

Path Parameters

  * organizationIdCopy link to organizationId

Type: integerFormat: int64

required

ID of organization that timeseries data is associated with

  * projectIdCopy link to projectId

Type: integerFormat: int64

required

ID of project that timeseries data is associated with

  * dataSourceIdCopy link to dataSourceId

Type: integerFormat: int64

required

ID of data source that timeseries data is associated with

Body

required

Selected Content Type:application/json

Timeseries request DTO

  * fileNameCopy link to fileName

Type: string

required

  * fileSizeCopy link to fileSize

Type: integer | string` Pattern:  ^-?(?:0|[1-9]\d*)$`Format: int64

Responses

  * 200Copy link to 200

{UploadId}

  * 401Copy link to 401

Unauthorized - Invalid or missing authentication token

  * 403Copy link to 403

Forbidden - Insufficient permissions

  * 500Copy link to 500

Internal Server Error

Request Example for post/organizations/_{organizationId}_
/projects/_{projectId}_ /datasources/_{dataSourceId}_ /timeseries/upload/start

Shell Curl

    
    
    curl https://deeplynx.inl.gov/api/v1/organizations/1/projects/1/datasources/1/timeseries/upload/start \
      --request POST \
      --header 'Content-Type: application/json' \
      --data '{
      "fileName": "",
      "fileSize": 1
    }'
    

Test Request(post
/organizations/{organizationId}/projects/{projectId}/datasources/{dataSourceId}/timeseries/upload/start)

Status: 200Status: 401Status: 403Status: 500

No Body

{UploadId}

### Upload Timeseries Chunk

​Copy link

Path Parameters

  * organizationIdCopy link to organizationId

Type: integerFormat: int64

required

ID of organization that timeseries data is associated with

  * projectIdCopy link to projectId

Type: integerFormat: int64

required

ID of project that timeseries data is associated with

  * dataSourceIdCopy link to dataSourceId

Type: integerFormat: int64

required

ID of data source that timeseries data is associated with

Body

required

multipart/form-data

Chunk number from form

  * Type: object

    * chunkCopy link to chunk

Type: stringFormat: binary

binary data, used to describe files

    * chunkNumberCopy link to chunkNumber

Type: integer | string` Pattern:  ^-?(?:0|[1-9]\d*)$`Format: int32

    * uploadIdCopy link to uploadId

Type: string

Responses

  * 200Copy link to 200

{ChunkUploadStatus}

  * 401Copy link to 401

Unauthorized - Invalid or missing authentication token

  * 403Copy link to 403

Forbidden - Insufficient permissions

  * 500Copy link to 500

Internal Server Error

Request Example for post/organizations/_{organizationId}_
/projects/_{projectId}_ /datasources/_{dataSourceId}_ /timeseries/upload/chunk

Shell Curl

    
    
    curl https://deeplynx.inl.gov/api/v1/organizations/1/projects/1/datasources/1/timeseries/upload/chunk \
      --request POST \
      --header 'Content-Type: multipart/form-data' \
      --form 'uploadId=' \
      --form 'chunkNumber=1'
    

Test Request(post
/organizations/{organizationId}/projects/{projectId}/datasources/{dataSourceId}/timeseries/upload/chunk)

Status: 200Status: 401Status: 403Status: 500

No Body

{ChunkUploadStatus}

### Complete Timeseries Upload

​Copy link

Path Parameters

  * organizationIdCopy link to organizationId

Type: integerFormat: int64

required

ID of organization that timeseries data is associated with

  * projectIdCopy link to projectId

Type: integerFormat: int64

required

ID of project that timeseries data is associated with

  * dataSourceIdCopy link to dataSourceId

Type: integerFormat: int64

required

ID of data source that timeseries data is associated with

Body

required

Selected Content Type:application/json

Timeseries request DTO

  * fileNameCopy link to fileName

Type: string

required

  * uploadIdCopy link to uploadId

Type: string

required

  * totalChunksCopy link to totalChunks

Type: integer | string` Pattern:  ^-?(?:0|[1-9]\d*)$`Format: int32

Responses

  * 200

{TimeseriesUploadRecord}

Selected Content Type:text/plain

  * 401Copy link to 401

Unauthorized - Invalid or missing authentication token

  * 403Copy link to 403

Forbidden - Insufficient permissions

  * 500Copy link to 500

Internal Server Error

Request Example for post/organizations/_{organizationId}_
/projects/_{projectId}_ /datasources/_{dataSourceId}_
/timeseries/upload/complete

Shell Curl

    
    
    curl https://deeplynx.inl.gov/api/v1/organizations/1/projects/1/datasources/1/timeseries/upload/complete \
      --request POST \
      --header 'Content-Type: application/json' \
      --data '{
      "uploadId": "",
      "fileName": "",
      "totalChunks": 1
    }'
    

Test Request(post
/organizations/{organizationId}/projects/{projectId}/datasources/{dataSourceId}/timeseries/upload/complete)

Status: 200Status: 401Status: 403Status: 500

Show Schema

    
    
    {
      "id": 1,
      "name": "string",
      "description": "string",
      "uri": null,
      "properties": "string",
      "objectStorageId": null,
      "originalId": "string",
      "classId": null,
      "dataSourceId": 1,
      "projectId": 1,
      "organizationId": 1,
      "lastUpdatedAt": "2026-02-10T18:44:53.109Z",
      "lastUpdatedBy": null,
      "isArchived": true,
      "fileType": null,
      "tags": [
        {
          "id": 1,
          "name": "string"
        }
      ]
    }

{TimeseriesUploadRecord}

### Append File to DuckDB Table

​Copy link

Path Parameters

  * organizationIdCopy link to organizationId

Type: integerFormat: int64

required

ID of organization that timeseries data is associated with

  * projectIdCopy link to projectId

Type: integerFormat: int64

required

ID of project that timeseries data is associated with

  * dataSourceIdCopy link to dataSourceId

Type: integerFormat: int64

required

ID of data source that timeseries data is associated with

Query Parameters

  * tableNameCopy link to tableName

Type: string

Name of the duckDB table on which the timeseries data is encoded

Body

required

multipart/form-data

Timeseries file

  * fileCopy link to file

Type: stringFormat: binary

binary data, used to describe files

Responses

  * 200

Selected Content Type:text/plain

  * 401Copy link to 401

Unauthorized - Invalid or missing authentication token

  * 403Copy link to 403

Forbidden - Insufficient permissions

  * 500Copy link to 500

Internal Server Error

Request Example for patch/organizations/_{organizationId}_
/projects/_{projectId}_ /datasources/_{dataSourceId}_ /timeseries/append

Shell Curl

    
    
    curl 'https://deeplynx.inl.gov/api/v1/organizations/1/projects/1/datasources/1/timeseries/append?tableName=' \
      --request PATCH \
      --header 'Content-Type: multipart/form-data'
    

Test Request(patch
/organizations/{organizationId}/projects/{projectId}/datasources/{dataSourceId}/timeseries/append)

Status: 200Status: 401Status: 403Status: 500

Show Schema

    
    
    string

### Get Every Nth Timeseries Table Row

​Copy link

Path Parameters

  * organizationIdCopy link to organizationId

Type: integerFormat: int64

required

ID of organization that timeseries data is associated with

  * projectIdCopy link to projectId

Type: integerFormat: int64

required

ID of project that timeseries data is associated with

  * dataSourceIdCopy link to dataSourceId

Type: integerFormat: int64

required

ID of data source that timeseries data is associated with

Query Parameters

  * tableNameCopy link to tableName

Type: string

Name of the duckDB table on which the timeseries data is encoded

  * rowNumberCopy link to rowNumber

Type: string

every nth row to get (row number 4 = every 4th row)

  * fileTypeCopy link to fileType

Type: string

The type of file to convert query to

Responses

  * 200Copy link to 200

  * 401Copy link to 401

Unauthorized - Invalid or missing authentication token

  * 403Copy link to 403

Forbidden - Insufficient permissions

  * 500Copy link to 500

Internal Server Error

Request Example for get/organizations/_{organizationId}_
/projects/_{projectId}_ /datasources/_{dataSourceId}_ /timeseries/interpolate

Shell Curl

    
    
    curl 'https://deeplynx.inl.gov/api/v1/organizations/1/projects/1/datasources/1/timeseries/interpolate?tableName=&rowNumber=&fileType='
    

Test Request(get
/organizations/{organizationId}/projects/{projectId}/datasources/{dataSourceId}/timeseries/interpolate)

Status: 200Status: 401Status: 403Status: 500

No Body

### Exports Table to File

​Copy link

Path Parameters

  * organizationIdCopy link to organizationId

Type: integerFormat: int64

required

ID of organization that timeseries data is associated with

  * projectIdCopy link to projectId

Type: integerFormat: int64

required

ID of project that timeseries data is associated with

  * dataSourceIdCopy link to dataSourceId

Type: integerFormat: int64

required

ID of data source that timeseries data is associated with

Query Parameters

  * tableNameCopy link to tableName

Type: string

Name of the duckDB table on which the timeseries data is encoded

  * fileTypeCopy link to fileType

Type: string

The type of file to convert query to

Responses

  * 200Copy link to 200

  * 401Copy link to 401

Unauthorized - Invalid or missing authentication token

  * 403Copy link to 403

Forbidden - Insufficient permissions

  * 500Copy link to 500

Internal Server Error

Request Example for get/organizations/_{organizationId}_
/projects/_{projectId}_ /datasources/_{dataSourceId}_ /timeseries/export

Shell Curl

    
    
    curl 'https://deeplynx.inl.gov/api/v1/organizations/1/projects/1/datasources/1/timeseries/export?tableName=&fileType='
    

Test Request(get
/organizations/{organizationId}/projects/{projectId}/datasources/{dataSourceId}/timeseries/export)

Status: 200Status: 401Status: 403Status: 500

No Body

## Notification  (Collapsed)

​Copy link

Notifications

Notification Operations

  * post/notifications/email

### Send Email

​Copy link

Query Parameters

  * emailCopy link to email

Type: string

  * nameCopy link to name

Type: string

Responses

  * 200Copy link to 200

OK

  * 401Copy link to 401

Unauthorized - Invalid or missing authentication token

  * 403Copy link to 403

Forbidden - Insufficient permissions

  * 500Copy link to 500

Internal Server Error

Request Example for post/notifications/email

Shell Curl

    
    
    curl 'https://deeplynx.inl.gov/api/v1/notifications/email?email=&name=' \
      --request POST
    

Test Request(post /notifications/email)

Status: 200Status: 401Status: 403Status: 500

No Body

OK

##  Models

Show More


