import json
import os
import datetime
import requests
import boto3

# Initialize AWS S3 client
s3_client = boto3.client("s3")

# --- Configuration ---
GRAPHQL_API_URL = os.environ.get(
    "GRAPHQL_API_URL", "https://app.elitesportsbets.com/api/open/graphql"
)
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME", "esb-new-landing")

# --- GraphQL Queries Definitions ---

# Query 1: GetPickStats
GET_PICK_STATS_QL = """
  query gqlQuery($sportId: Int) {
    GetPickStats(SportId: $sportId) {
      percentage7D
      percentageALL
    }
  }
"""
# Variables for GetPickStats
SPORT_ID = int(
    os.environ.get("SPORT_ID", "0")
)  # Example SportId, make sure it's an integer

# Query 2: ListPicks
# This version assumes 'bringOnlyId' is false and no fields are hidden.
# If you need a different set of fields, modify this query string directly.
LIST_PICKS_QL_FULL_FIELDS = """
  query gqlQuery($page: Int, $pageSize: Int, $sort: [String], $sortDir: [SORT_DIRECTION], $filter: PickFilter) {
    ListPicks(page: $page, pageSize: $pageSize, sort: $sort, sortDir: $sortDir, filter: $filter) {
      page
      pageSize
      totalPages
      totalRecords
      rows {
        id
        SportId
        AwayCompetitorId
        HomeCompetitorId
        status
        summary
        matchTime
        title
        SportFld {
          id
          shortTitle
          title
        }
        AwayCompetitorFld {
          id
          logo
          name
        }
        HomeCompetitorFld {
          id
          logo
          name
        }
      }
    }
  }
"""
# Variables for ListPicks
LIST_PICKS_PAGE = int(os.environ.get("LIST_PICKS_PAGE", "0"))
LIST_PICKS_PAGE_SIZE = int(os.environ.get("LIST_PICKS_PAGE_SIZE", "100"))
LIST_PICKS_SORT_FIELD = os.environ.get("LIST_PICKS_SORT_FIELD", "matchTime")
LIST_PICKS_SORT_DIRECTION = os.environ.get("LIST_PICKS_SORT_DIRECTION", "DESC")
LIST_PICKS_FILTER_JSON = os.environ.get(
    "LIST_PICKS_FILTER_JSON", '{"status":["CORRECT","INCORRECT","PUSH"]}'
)  # Default to empty filter


def execute_graphql_query(query, variables, output_prefix):
    """
    Helper function to execute a single GraphQL query and upload its result to S3.
    Returns True on success, False on failure.
    """
    print(f"Executing GraphQL query for: {output_prefix}")
    try:
        payload = {"query": query, "variables": variables}
        headers = {
            "Content-Type": "application/json"
            # Add any necessary authorization headers here, e.g.:
            # 'Authorization': f'Bearer {os.environ.get("GRAPHQL_API_KEY")}'
        }

        response = requests.post(GRAPHQL_API_URL, json=payload, headers=headers)
        response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)

        data = response.json()

        if "errors" in data:
            print(f"GraphQL errors encountered for {output_prefix}: {data['errors']}")
            return False

        extracted_data = None
        if output_prefix == "pick_stats":
            extracted_data = data.get("data", {}).get("GetPickStats")
        elif output_prefix == "list_picks":
            list_picks_data = data.get("data", {}).get("ListPicks")
            if list_picks_data and "rows" in list_picks_data:
                extracted_data = list_picks_data["rows"]
                print(
                    f"{output_prefix} fetched {len(extracted_data)} records out of {list_picks_data.get('totalRecords', 'N/A')}"
                )
            else:
                print(f"No '{output_prefix}' data or 'rows' found in GraphQL response.")

        if not extracted_data:
            print(
                f"No relevant data found for query '{output_prefix}'. Skipping S3 upload."
            )
            return True  # Consider it a success if no data, but no error

        current_utc_time = datetime.datetime.utcnow()
        # Save to S3 under /data/latest
        s3_key_prefix = "data/latest"
        s3_file_name = f"{s3_key_prefix}/{output_prefix}.json"

        json_data = json.dumps(extracted_data, indent=2)

        # Save to S3
        # s3_client.put_object(
        #     Bucket=S3_BUCKET_NAME,
        #     Key=s3_file_name,
        #     Body=json_data,
        #     ContentType="application/json",
        # )

        print(
            f"Successfully uploaded {output_prefix} data to s3://{S3_BUCKET_NAME}/{s3_file_name}"
        )

        # Save to local file in ./data/latest directory
        local_dir = os.path.join(os.getcwd(), "data", "latest")
        os.makedirs(local_dir, exist_ok=True)
        local_file_name = os.path.join(local_dir, f"{output_prefix}.json")
        with open(local_file_name, "w") as local_file:
            local_file.write(json_data)
        print(f"Successfully saved {output_prefix} data locally as {local_file_name}")
        return True

    except requests.exceptions.RequestException as e:
        print(f"HTTP Request failed for {output_prefix}: {e}")
        return False
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON response for {output_prefix}: {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred for {output_prefix}: {e}")
        return False


def lambda_handler(event, context):
    """
    Main handler for the Lambda function.
    Executes both GetPickStats and ListPicks GraphQL queries and uploads
    their results to separate files in S3.
    """
    print("Starting execution of both GraphQL queries.")
    overall_status = True

    # --- Execute GetPickStats Query ---
    pick_stats_variables = {"sportId": SPORT_ID}
    if not execute_graphql_query(GET_PICK_STATS_QL, pick_stats_variables, "pick_stats"):
        overall_status = False
        print("GetPickStats query failed.")

    # --- Execute ListPicks Query ---
    try:
        filter_obj = json.loads(LIST_PICKS_FILTER_JSON)
    except json.JSONDecodeError:
        print(
            f"Warning: LIST_PICKS_FILTER_JSON is not valid JSON: {LIST_PICKS_FILTER_JSON}. Using empty filter for ListPicks."
        )
        filter_obj = {}

    list_picks_variables = {
        "page": LIST_PICKS_PAGE,
        "pageSize": LIST_PICKS_PAGE_SIZE,
        "sort": [LIST_PICKS_SORT_FIELD],
        "sortDir": [LIST_PICKS_SORT_DIRECTION],
        "filter": filter_obj,
    }
    if not execute_graphql_query(
        LIST_PICKS_QL_FULL_FIELDS, list_picks_variables, "list_picks"
    ):
        overall_status = False
        print("ListPicks query failed.")

    if overall_status:
        return {
            "statusCode": 200,
            "body": json.dumps(
                {"message": "Both GraphQL queries executed and results uploaded to S3."}
            ),
        }
    else:
        return {
            "statusCode": 500,
            "body": json.dumps(
                {"message": "One or more GraphQL queries failed to execute or upload."}
            ),
        }


if __name__ == "__main__":
    lambda_handler(None, None)
