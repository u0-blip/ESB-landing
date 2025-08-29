import json
import os

import boto3
import requests
from bs4 import BeautifulSoup

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
)


def execute_graphql_query(query, variables, output_prefix, data_dict):
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
            # --- update win-rate, and save locally ---

            try:
                if extracted_data and "percentageALL" in extracted_data:
                    data_dict["percentageALL"] = extracted_data["percentageALL"]
                else:
                    print("Could not find win-rate element or percentageALL in data.")
            except Exception as e:
                print(f"Failed to update index.html with win-rate: {e}")

        elif output_prefix == "list_picks":
            list_picks_data = data.get("data", {}).get("ListPicks")
            if list_picks_data and "rows" in list_picks_data:
                extracted_data = list_picks_data["rows"]
                print(
                    f"{output_prefix} fetched {len(extracted_data)} records out of {list_picks_data.get('totalRecords', 'N/A')}"
                )
                win_streak = 0
                for row in extracted_data:
                    if row["status"] == "CORRECT":
                        win_streak += 1
                    else:
                        break
                print(f"Win streak: {win_streak}")
                data_dict["winStreak"] = win_streak

            else:
                print(f"No '{output_prefix}' data or 'rows' found in GraphQL response.")

        if not extracted_data:
            print(
                f"No relevant data found for query '{output_prefix}'. Skipping S3 upload."
            )
            return True  # Consider it a success if no data, but no error

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


def update_index_html(data_dict):

    s3_index_key = "index.html"
    index_obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=s3_index_key)
    index_html = index_obj["Body"].read().decode("utf-8")

    soup = BeautifulSoup(index_html, "html.parser")
    win_rate_elem = soup.find(id="win-rate")
    hero_text_elem = soup.find(id="hero-text")
    win_streak_elem = soup.find(id="win-streak")

    win_rate_elem.string = f"{data_dict['percentageALL']}%"
    hero_text_elem.string = f"Join 1,200+ successful bettors getting data-driven NBA tips with {data_dict['percentageALL']}% win rate and 25% ROI"
    win_streak_elem.string = f"{data_dict['winStreak']}"

    # Save modified HTML to /data/latest/index.html
    local_dir = os.path.join(os.getcwd(), "data", "latest")
    os.makedirs(local_dir, exist_ok=True)
    local_index_path = os.path.join(local_dir, "index.html")
    with open(local_index_path, "w") as f:
        f.write(str(soup))
    print(f"Updated index.html with win-rate and saved to {local_index_path}")
    # Upload the modified index.html back to S3
    s3_client.put_object(
        Bucket=S3_BUCKET_NAME,
        Key=s3_index_key,
        Body=str(soup),
        ContentType="text/html",
    )
    print(f"Uploaded updated index.html to s3://{S3_BUCKET_NAME}/{s3_index_key}")


def lambda_handler(event, context):
    """
    Main handler for the Lambda function.
    Executes both GetPickStats and ListPicks GraphQL queries and uploads
    their results to separate files in S3.
    """
    print("Starting execution of both GraphQL queries.")
    overall_status = True
    data_dict = {}

    # --- Execute GetPickStats Query ---
    pick_stats_variables = {"sportId": SPORT_ID}
    if not execute_graphql_query(
        GET_PICK_STATS_QL, pick_stats_variables, "pick_stats", data_dict
    ):
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
        LIST_PICKS_QL_FULL_FIELDS, list_picks_variables, "list_picks", data_dict
    ):
        overall_status = False
        print("ListPicks query failed.")

    update_index_html(data_dict)

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
