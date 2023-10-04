"""
Filename: youtube_data_processing.py
Authors: Marcelo Amaral
Created: Aug 1, 2023
Last Updated: Aug 4, 2023

Description:
This script collects, processes, and organizes YouTube data into two dataframes, one for channel data and another for video data. 
It uses the YouTube Data API for data collection and includes various channel and video attributes such as description, video count, 
view count, subscriber count, video title, publish date, like count, and comment count. 

The script includes several functions for processing the YouTube data, including calculating and appending additional statistics and 
ratios, and storing the processed data in .xlsx files. It also handles JSON data for maintaining a list of channels and videos that 
have been processed. 

For detailed descriptions of each function, refer to the function-level docstrings or the script documentation.
"""

import requests
import json
import pandas as pd
import os


def get_channel_statistics(api_key, channel_id):
    """
    Retrieves the statistics for a given YouTube channel using the YouTube Data API. 
    The statistics include the number of subscribers, total views, and total videos, among other data.
    """
    base_url = "https://www.googleapis.com/youtube/v3/channels"
    params = {
        "part": "snippet,brandingSettings,contentDetails,statistics,topicDetails,status",
        "id": channel_id,
        "key": api_key
    }
    response = requests.get(base_url, params=params)
    data = response.json()
    #print(data)

    return data


def write_channel_video_list_to_file(channel_id, video_ids):
    """
    Writes a list of video IDs to a JSON file. 
    Each video ID is associated with a flag indicating whether the video's data has been fetched from the API.
    """
    
    # Create a list of dictionaries, each containing the video ID and a fetched_video flag
    video_list = [{"VideoID": video_id, "fetched_video": False} for video_id in video_ids]

    # Convert list to JSON
    json_data = json.dumps(video_list, indent=4)

    # Write JSON data to file
    with open(f"{channel_id}.json", "w") as file:
        file.write(json_data)


def get_channel_videos_list(channel_id, api_key):
    """
    Retrieves a list of video IDs for the videos uploaded by a given YouTube channel. 
    This is done using the YouTube Data API's search functionality, 
    which returns a list of videos in reverse chronological order (i.e., newest videos first).
    """
    base_search_url = 'https://www.googleapis.com/youtube/v3/search?'

    first_url = base_search_url+'key={}&channelId={}&part=snippet,id&order=date&maxResults=25'.format(api_key, channel_id)

    video_ids = []
    url = first_url
    while True:
        response = requests.get(url)
        data = json.loads(response.text)
        if 'error' in data:
            if data['error']['code'] == 403 and 'quota' in data['error']['message']:
                print("Quota exceeded. Please try again later.")
                raise Exception("Quota exceeded get channel list. Please try again later.")
                return None
        if 'items' in data:
            for video in data['items']:
                if video['id']['kind'] == "youtube#video":
                    video_ids.append(video['id']['videoId'])

            try:
                next_page_token = data['nextPageToken']
                url = first_url + '&pageToken={}'.format(next_page_token)
            except KeyError:
                break
        else:
            print(f"No videos found for channel {channel_id}")
            return None
    return video_ids

def get_channel_video(api_key, video_id):
    """
    Retrieves detailed data for a single video using the YouTube Data API. 
    The data includes the video's title, description, duration, view count, like count, comment count, and more.    
    """
    #try:
    base_url = "https://www.googleapis.com/youtube/v3/videos"
    parts = [
        "contentDetails", "id", "liveStreamingDetails", "localizations",
        "player", "recordingDetails", "snippet", "statistics",
        "status", "topicDetails"
    ]
    params = {
        "part": ",".join(parts),
        "id": video_id,
        "key": api_key
    }
    response = requests.get(base_url, params=params)
    data = response.json()
    #print(data)
    if 'error' in data:
        if data['error']['code'] == 403 and 'quota' in data['error']['message']:
            print("Quota exceeded. Please try again later.")
            raise Exception("Quota exceeded get channel video. Please try again later.")
            return None

    return data
    #except Exception as e:
    #    print(f"An error occurred: {e}")
    #    return None


def process_channels(api_key, max_channels, api_data_file, channels_file_json):
    """
    Processes a list of YouTube channels, fetching their statistics and videos using the YouTube Data API. 
    The data is written to a JSON file. 
    The function also manages a quota limit by keeping track of the number of channels processed and stopping when a maximum limit is reached.
    """
    if not os.path.exists(api_data_file):
        # Create an empty DataFrame
        df = pd.DataFrame()
        df.to_json(api_data_file, orient='records', lines=True)
    else:
        df = pd.read_json(api_data_file, lines=True)

    with open(channels_file_json) as f:
        ranked_channels = json.load(f)

    channels_processed = 0

    for i, channel_info in enumerate(ranked_channels):
        if channels_processed >= max_channels:
            break

        channel_id = channel_info['channelID']
        fetched_videos = channel_info['fetched_videos']
        fetched_statistics = channel_info['fetched_statistics']

        if not fetched_statistics:
            channel_statistics = get_channel_statistics(api_key, channel_id)
            if df.empty:
                new_row = pd.DataFrame({channel_id: [{'yt_api': {'videos': [], 'statistics': channel_statistics}}]})
                df = pd.concat([df, new_row], ignore_index=True)
            else:
                if channel_id not in df.columns:
                    df[channel_id] = None
                df.at[0, channel_id] = {'yt_api': {'videos': [], 'statistics': channel_statistics}}

            channel_info['fetched_statistics'] = True
            df.to_json(api_data_file, lines=True, orient='records')

            with open(channels_file_json, 'w') as f:
                json.dump(ranked_channels, f)
                
        if not fetched_videos:
            if not os.path.exists(f"{channel_id}.json"):
                channel_videos = get_channel_videos_list(channel_id, api_key)
                write_channel_video_list_to_file(channel_id, channel_videos)

            with open(f"{channel_id}.json", "r") as file:
                channel_videos = json.load(file)

            if channel_videos is None:
                print(f"Failed to get videos for channel {channel_id}, skipping...")
                continue

            all_videos_feched = True
            for video in channel_videos:
                video_id = video['VideoID']
                fetched_video = video['fetched_video']
                if not fetched_video:
                    video_data = get_channel_video(api_key,video_id)
                    # Check if video_data is not None before updating
                    if video_data is not None:
                        channel_data = df.at[0, channel_id]
                        channel_data['yt_api']['videos'].append(video_data)
                        df.at[0, channel_id] = channel_data
                        df.to_json(api_data_file, lines=True, orient='records')
                        
                        video['fetched_video'] = True
                        with open(f"{channel_id}.json", "w") as file:
                            json.dump(channel_videos, file)
                    else:
                        all_videos_feched = False
            if all_videos_feched:
                channel_info['fetched_videos'] = True
                with open(channels_file_json, 'w') as f:
                    json.dump(ranked_channels, f)

        channels_processed += 1
    print(channels_processed)



def fetch_youtube_data(api_key, api_data_file, channels_file_json, maxChannels, processVideo=True):
    """
    fetch_youtube_data is a function designed to retrieve data from the YouTube Data API, 
    specifically focusing on channel statistics and video details. It takes four parameters: api_key, api_data_file, channels_file_json, 
    and maxChannels.
        api_key is used to authenticate with the YouTube Data API.
        api_data_file is the path to a JSON file where the retrieved data will be stored.
        channels_file_json is the path to a JSON file containing the list of channel IDs to be processed.
        maxChannels is an integer value representing the maximum number of channels to process.
    The function iterates over each channel ID in the provided list. For each channel, it checks if the channel's statistics 
    and videos have already been fetched. If not, it uses the YouTube Data API to fetch the data and updates the 
    DataFrame and JSON files accordingly. It also keeps track of the number of channels processed and loaded, and prints these numbers at the end.
    This function is particularly useful for large-scale data collection projects where API quota limits must be managed and 
    redundancy in data fetching should be avoided. It organizes the fetched data in a structured format, making subsequent data analysis easier.
    """

    if not os.path.exists(api_data_file):
        # Create an empty DataFrame
        df = pd.DataFrame()

        # Save it as a JSON file
        df.to_json(api_data_file, orient='records', lines=True)
    else:
        # If the file exists, load it
        df = pd.read_json(api_data_file, lines=True)

    # to process from ranked channels or the other json with choosen channel ids
    with open(channels_file_json) as f:
        ranked_channels = json.load(f)


    channelsProcessed = 0
    channelsLoaded = 0

    # Loop through each channel in ranked_channels
    for i, channel_info in enumerate(ranked_channels):
        channel_id = channel_info['channelID']
        fetched_videos = channel_info['fetched_videos']
        fetched_statistics = channel_info['fetched_statistics']

        # If we've processed the maximum number of channels, stop processing
        if channelsProcessed >= maxChannels:
            break

        # If we haven't fetched the statistics data yet, fetch it
        if not fetched_statistics:
            channel_statistics = get_channel_statistics(api_key, channel_id)
            
            # Add the updated data to the data structure
            if df.empty:
                # If the DataFrame is empty, create a new row with channel_id as a column and the channel data as the value
                new_row = pd.DataFrame({channel_id: [{'yt_api': {'videos': [], 'statistics': channel_statistics}}]})
                df = pd.concat([df, new_row], ignore_index=True)
            else:
                if channel_id not in df.columns:
                    df[channel_id] = None
                df.at[0, channel_id] = {'yt_api': {'videos': [], 'statistics': channel_statistics}}
        
        
            # Update the fetched_statistics flag
            channel_info['fetched_statistics'] = True
            # Write the updated data back into the JSON file
            df.to_json(api_data_file, lines=True, orient='records')

            # Write the updated ranked_channels data back into its JSON file
            with open(channels_file_json, 'w') as f:
                json.dump(ranked_channels, f)
        
        # If processVideo is False, skip the video processing part
        if not processVideo:
            channelsLoaded += 1
            continue
        
        if not fetched_videos:
            # Check if file already exists
            if not os.path.exists(f"{channel_id}.json"):
                # Use get_channel_videos_list to get a list of video IDs
                channel_videos = get_channel_videos_list(channel_id, api_key)

                # If not, pass the list of video IDs to the new function to write it to a file
                write_channel_video_list_to_file(channel_id, channel_videos)

            # Open the file and read the JSON data
            with open(f"{channel_id}.json", "r") as file:
                channel_videos = json.load(file)

            

            if channel_videos is None:
                print(f"Failed to get videos for channel {channel_id}, skipping...")
                continue

            all_videos_feched = True
            # loop through the channel_videos
            for video in channel_videos:            
                video_id = video['VideoID']
                fetched_video = video['fetched_video']
                # If we haven't fetched the video data yet, fetch it
                if not fetched_video:
                    video_data = get_channel_video(api_key,video_id)
                    if not fetched_video:
                        # Add the updated data to the data structure
                        channel_data = df.at[0, channel_id]
                        channel_data['yt_api']['videos'].append(video_data)
                        df.at[0, channel_id] = channel_data


                        # Write the updated data back into the JSON file
                        df.to_json(api_data_file, lines=True, orient='records')
                        
                        # Mark the video as fetched in the video list
                        video['fetched_video'] = True
                        # Write the updated video list back to the JSON file
                        with open(f"{channel_id}.json", "w") as file:
                            json.dump(channel_videos, file)
                    else:
                        all_videos_feched = False
            if all_videos_feched :
                # Update the fetched_videos flag
                channel_info['fetched_videos'] = True
                # Write the updated ranked_channels data back into its JSON file
                with open(channels_file_json, 'w') as f:
                    json.dump(ranked_channels, f)
            # Increment the number of channels processed
            channelsProcessed += 1
        # Increment the number of channels loaded
        channelsLoaded += 1
    print(channelsProcessed)
    print(channelsLoaded)
    



def create_flat_tables_youtube_data(df_api, df_trend, df_category, xlsx_channel_name, xlsx_channel_video):
    """
    create_flat_tables_youtube_data: Creates two flat tables for the YouTube data. The function uses the API data, trending data, 
    and category data to create two tables: one for the channel data and another for the video data. 
    The function also updates the tables with information on whether a channel has a trending video and the number of trending videos a channel has. 
    The tables are then written to .xlsx files.
    """

    # Create empty dataframes for the channel and video tables
    channel_table = pd.DataFrame()
    video_table = pd.DataFrame()

    # Create a category dictionary
    category_dict = {item['id']: item['snippet']['title'] for item in df_category['items']}

    # Loop through each channel in df_api
    for channel_id in df_api.columns:
        channel_data = df_api[channel_id][0]['yt_api']
        # Extract channel data
        try:
            channel_info = channel_data['statistics']['items'][0]
        except KeyError:
            print(f"KeyError: 'items' not found in channel data for channel {channel_id}.")
            print("Channel data:", channel_data)
            continue

        # Safely access 'topicDetails' with a default value of an empty dictionary
        topic_details = channel_info.get('topicDetails', {})

        channel_row = {
            'channelId': channel_id,
            'channelTitle': channel_info['snippet']['title'],
            'description': channel_info['snippet']['description'],
            'publishedAt': channel_info['snippet']['publishedAt'],
            'videoCount': channel_info['statistics']['videoCount'],
            'viewCount': channel_info['statistics'].get('viewCount', ''),  # not all channels may have a view count
            'subscriberCount': channel_info['statistics']['subscriberCount'],
            'country': channel_info['snippet'].get('country', ''),  # not all channels have a country
            'customUrl': channel_info['snippet'].get('customUrl', ''),  # not all channels have a customUrl
            'topicCategories': topic_details.get('topicCategories', []),  # Safely access 'topicCategories' with a default value of an empty list
            'madeForKids': channel_info['status'].get('madeForKids', '0'), # not all videos have madeForKids
            'keywords': channel_info['brandingSettings'].get('channel', {}).get('keywords', ''),  # not all channels have keywords
            'hasVideoTrending': False,
            'numberVideoTrending': 0
        }
        #channel_table = channel_table.append(channel_row, ignore_index=True)
        new_row = pd.DataFrame([channel_row])
        channel_table = pd.concat([channel_table, new_row], ignore_index=True)


        # Extract video data
        for video in channel_data['videos']:
            if video is None or 'error' in video:  # Skip if video is None or an error occurred- it seems can occur some errors with the call like service is currently unavailable
                print("Empty video data encountered.")
                continue
            try:
                video_info = video['items'][0]
            except KeyError:
                print("KeyError: 'items' not found in video data.")
                print("Video data:", video)
                continue

            video_row = {
                'videoId': video_info['id'],
                'title': video_info['snippet']['title'],
                'description': video_info['snippet']['description'],
                'publishedAt': video_info['snippet']['publishedAt'],
                'channelId': video_info['snippet']['channelId'],
                'categoryId': video_info['snippet']['categoryId'],
                # Use the category dictionary to get the category name
                'category': category_dict[video_info['snippet']['categoryId']],
                'viewCount': video_info['statistics'].get('viewCount', []),  # not all videos may have viewCount
                'likeCount': video_info['statistics'].get('likeCount', []),  # not all videos have likeCount
                'commentCount': video_info['statistics'].get('commentCount', '0'), # not all videos have commentCount
                'tags': video_info['snippet'].get('tags', []),  # not all videos have tags
                'channelTitle': video_info['snippet']['channelTitle'],
                'thumbnails': video_info['snippet']['thumbnails'],
                'isTrending': False,
                'duration': video_info['contentDetails']['duration'],
                'dimension': video_info['contentDetails']['dimension'],
                'definition': video_info['contentDetails']['definition'],
                'caption': video_info['contentDetails']['caption'],
                'licensedContent': video_info['contentDetails']['licensedContent'],
                'projection': video_info['contentDetails']['projection'],
                'uploadStatus': video_info['status']['uploadStatus'],
                'privacyStatus': video_info['status']['privacyStatus'],
                'license': video_info['status']['license'],
                'embeddable': video_info['status']['embeddable'],
                'publicStatsViewable': video_info['status']['publicStatsViewable'],
                'madeForKids': video_info['status'].get('madeForKids', '0'), # not all videos have madeForKids
                'favoriteCount': video_info['statistics'].get('favoriteCount', '0'),  # not all videos have favoriteCount
                'topicCategories': video_info.get('topicDetails', {}).get('topicCategories', [])  # not all videos have topicCategories
            }
            #video_table = video_table.append(video_row, ignore_index=True)
            new_row = pd.DataFrame([video_row])
            video_table = pd.concat([video_table, new_row], ignore_index=True)
            # Initialize an empty list outside the loop
            # video_rows = []
            # Inside the loop, append dictionaries to the list instead of appending rows to the DataFrame
            #video_rows.append(video_row)
            # After the loop, convert the list of dictionaries into a DataFrame
            #video_table = pd.DataFrame(video_rows)

    # Loop through each channel in df_trend
    for channel_id_trending in df_trend.columns:
        # Check if the trending channel_id is in the API data
        if channel_id_trending in df_api.columns:
            # Set hasVideoTrending to True in channel_table
            channel_table.loc[channel_table['channelId'] == channel_id_trending, 'hasVideoTrending'] = True
            channel_data_trend = df_trend[channel_id_trending][0]['US_trends']
            for video_trend in channel_data_trend:
                # Set isTrending to True in video_table
                video_table.loc[video_table['videoId'] == video_trend.get('video_id', '0'), 'isTrending'] = True
                # Increment numberVideoTrending  in channel_table
                channel_table.loc[channel_table['channelId'] == channel_id_trending, 'numberVideoTrending'] += 1

    # Write the tables to .xlsx files
    channel_table.to_excel(xlsx_channel_name, index=False)
    video_table.to_excel(xlsx_channel_video, index=False)




def channel_ids_csv_to_json(channels_id_csv_file, channels_id_json_file):
    """
    This function converts a CSV file of channel IDs into a JSON format file.
    
    Parameters:
    channels_id_csv_file (str): The name (with path, if not in the same directory) 
    of the input CSV file that contains the channel IDs.
    
    channels_id_json_file (str): The name (with path, if not in the same directory) 
    of the output JSON file to be created.
    
    The CSV file should contain a single column of YouTube channel IDs. 
    The resulting JSON file will contain an array of these IDs.
    """
    # Load the CSV file into a DataFrame
    df = pd.read_csv(channels_id_csv_file, header=None, names=['channel_id'])

    # Convert the DataFrame to a list
    channel_ids = df['channel_id'].tolist()

    # Initialize a list to store the formatted data
    formatted_data = []

    # Loop through each channel ID
    for channel_id in channel_ids:
        # Create a new dictionary with the structure you specified
        formatted_channel = {
            "channelID": channel_id,
            "fetched_videos": False,
            "fetched_statistics": False
        }

        # Append the new dictionary to formatted_data
        formatted_data.append(formatted_channel)

    # Write the formatted data to a JSON file
    with open(channels_id_json_file, 'w') as f:
        json.dump(formatted_data, f)
    print(f"File saved: {channels_id_json_file}.")



def merge_xlsx_files(xlsx_file1, xlsx_file2, xlsx_output_filename):
    """
    This function merges the contents of two XLSX files into a single new XLSX file.
    
    Parameters:
    xlsx_file1 (str): The name (with path, if not in the same directory) 
    of the first input XLSX file.
    
    xlsx_file2 (str): The name (with path, if not in the same directory) 
    of the second input XLSX file.
    
    xlsx_output_filename (str): The name (with path, if not in the same directory) 
    of the output XLSX file to be created.
    
    The two input XLSX files should have the same column structure. 
    The resulting XLSX file will contain all rows from both input files, 
    appended one after the other.
    """
    
    # Read the two xlsx files into dataframes
    df1 = pd.read_excel(xlsx_file1)
    df2 = pd.read_excel(xlsx_file2)
    
    # Concatenate the two dataframes into one
    merged_df = pd.concat([df1, df2], ignore_index=True)
    
    # Save the merged dataframe to a new xlsx file
    merged_df.to_excel(xlsx_output_filename, index=False)




def enriche_xlsx_youtube_data(xlsx_channels, xlsx_videos, xlsx_channels_enriched, xlsx_videos_enriched):
    """
    This function enriches YouTube channel and video data with calculated statistics.

    For each channel, the function calculates the mean and standard deviation of 'viewCount', 'likeCount',
    'commentCount', and 'favoriteCount'. It then merges this statistical data with the original channel data.

    For the video data, the function calculates the ratio of each video's 'viewCount', 'likeCount', 'commentCount',
    and 'favoriteCount' to the average count for the respective channel.

    The enriched data is saved back into new .xlsx files.

    Parameters:
    xlsx_channels (str): The path to the .xlsx file containing the channel data.
    xlsx_videos (str): The path to the .xlsx file containing the video data.
    xlsx_channels_enriched (str): The path to the .xlsx file to write the enriched channel data.
    xlsx_videos_enriched (str): The path to the .xlsx file to write the enriched video data.
    """
    
    # Load the data
    channel_data = pd.read_excel(xlsx_channels)
    video_data = pd.read_excel(xlsx_videos)

    # Convert counts to numeric
    for column in ['viewCount', 'likeCount', 'commentCount']:
        video_data[column] = pd.to_numeric(video_data[column], errors='coerce')
        video_data[column] = video_data[column].fillna(0)

    # Calculate statistics for video data
    video_stats = video_data.groupby('channelId')[['viewCount', 'likeCount', 'commentCount']].agg(['mean', 'std']).reset_index()

    # Flatten MultiIndex columns
    video_stats.columns = ['_'.join(col).strip() for col in video_stats.columns.values]
    video_stats.rename(columns={"channelId_": "channelId"}, inplace=True)

    # Merge these stats with the channel data
    channel_data_enriched = pd.merge(channel_data, video_stats, how='left', on='channelId')

    # Save the enriched channel data dataframe back into .xlsx files
    channel_data_enriched.to_excel(xlsx_channels_enriched, index=False)

    # Create a new dataframe for enriched video data
    video_data_enriched = video_data.merge(video_stats, how='left', on='channelId', suffixes=('', '_channel_avg'))
    for column in ['viewCount', 'likeCount', 'commentCount']:
        video_data_enriched[f'{column}_to_avg_{column}_ratio'] = video_data_enriched[column] / video_data_enriched[f'{column}_mean']

    # Save the enriched video data dataframe back into .xlsx files
    video_data_enriched.to_excel(xlsx_videos_enriched, index=False)



def get_top_videos(xlsx_videos, n=10):
    """
    This function retrieves the top n videos (based on viewCount) for each YouTube channel.

    The function loads the video data, converts 'viewCount' to numeric, and then groups the 
    videos by 'channelId'. For each group, it retrieves the top n videos with the highest 'viewCount'.

    The function returns a DataFrame containing the top n videos for each channel.

    Parameters:
    xlsx_videos (str): The path to the .xlsx file containing the video data.
    n (int): The number of top videos to retrieve for each channel.
    """
    
    # Load the video data
    video_data = pd.read_excel(xlsx_videos)

    # Convert 'viewCount' to numeric
    video_data['viewCount'] = pd.to_numeric(video_data['viewCount'], errors='coerce')
    video_data['viewCount'] = video_data['viewCount'].fillna(0)

    # Get the top n videos for each 'channelId' based on 'viewCount'
    top_videos = video_data.groupby('channelId').apply(lambda x: x.nlargest(n, 'viewCount')).reset_index(drop=True)

    return top_videos
