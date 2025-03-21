import requests
import json
from datetime import datetime,timedelta
import pandas as pd 
from io import BytesIO
import streamlit as st


headers = {
    'Accept': '*/*',
    'Accept-Encoding': 'gzip, deflate, br, zstd',
    'Accept-Language': 'en-US,en;q=0.9',
    'Origin': 'https://www.makemytrip.com',
    'Priority': 'u=1, i',
    'Referer': 'https://www.makemytrip.com/',
    'Sec-CH-UA': '"Chromium";v="130", "Brave";v="130", "Not?A_Brand";v="99"',
    'Sec-CH-UA-Mobile': '?0',
    'Sec-CH-UA-Platform': '"Windows"',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-site',
    'Sec-GPC': '1',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
    }

class StationCodeFetchError(Exception):
    def __init__(self, message="Unable to Fetch Station code"):
        self.message = message
        super().__init__(self.message)

def get_station(query: str):
    uri = f"https://ground-auto-suggest.makemytrip.com/rails/autosuggest/stations?version=v1&search_query={query}&limit=15"
    try:
        response = requests.get(uri, headers=headers).json()
        # Return up to 3 suggestions
        return [(item['dn'], item['irctc_code']) for item in response['data']['r']][:3]
    except Exception as e:
        raise StationCodeFetchError(f"Error fetching station code for query '{query}': {str(e)}")


def get_trains(source_code, destination_code, date):
    uri = f"https://railways.makemytrip.com/api/tbsWithAvailabilityAndRecommendation/{source_code}/{destination_code}/{date}"
    response_json = requests.get(uri, headers=headers).json()["trainBtwnStnsList"]
    return response_json

def extract(resp: json):
    train_data = []
    weekday_mapping = {
    'runningMon': 'Monday',
    'runningTue': 'Tuesday',
    'runningWed': 'Wednesday',
    'runningThu': 'Thursday',
    'runningFri': 'Friday',
    'runningSat': 'Saturday',
    'runningSun': 'Sunday'
    }

    for train in resp:
        for availability in train['tbsAvailability']:
            running_days = [day for key, day in weekday_mapping.items() if train[key] == "Y"]
            train_info = {
                'Train Name': train['trainName'],
                'Train Code': train['trainNumber'],
                'Source Code': train['frmStnCode'],
                'Destination Code': train['toStnCode'],
                'Date of Journey': availability["availablityDate"],
                'ArrivalTime': train['arrivalTime'],  
                'DepartureTime': train['departureTime'],
                'Last Updated': datetime.fromtimestamp(availability['lastUpdatedOnRaw'] / 1000).strftime('%Y-%m-%d %H:%M:%S'),  
                'Availablity': str("WL999") if availability['prettyPrintingAvailablityStatus'] is None else availability['prettyPrintingAvailablityStatus'],
                'Full Avail Status': availability['availablityStatus'],
                'predictionPercentage': str("NA") if availability['predictionPercentage'] is None else str(min(100,int(availability['predictionPercentage']))),
                'Class Name': availability['classType'],
                'Base Fare': availability['totalFare'],
                "Quota": availability["quota"],
                'RunningDays': ', '.join(running_days)
            }

            if train_info["Availablity"] == "WL999":
                train_info = {}
                continue
            train_data.append(train_info)
    return train_data

def sort_train_data(data):
    df = pd.DataFrame(data)

    df = df[df['Availablity'].notna()]

    def availability_sort_key(row):
        avail_status = row['Availablity']
        prediction = row['predictionPercentage']

        if "Available" in avail_status:
            return (1, 0)
        elif "RAC" in avail_status:
            return (2, 0)
        else:
            pred_value = -int(prediction) if prediction != "NA" else float('inf')
            return (3, pred_value)

    df['availability_sort_key'] = df.apply(availability_sort_key, axis=1)
    sorted_df = df.sort_values(by='availability_sort_key').drop(columns='availability_sort_key')

    return sorted_df

def convert_df_to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()


def convert_df_to_csv(df):
    output = BytesIO()
    df.to_csv(output, index=False)
    return output.getvalue()

def main():
    st.title('Train Availability Checker')
    source_count = st.slider("Number of Source Stations", min_value=1, max_value=6, value=1)
    
    source_stations = []
    cols = st.columns(source_count)
    for i, col in enumerate(cols):
        source_input = col.text_input(f"Source {i + 1}", "")
        if source_input:
            suggestions = get_station(source_input)
            selected_station = st.selectbox(f"Select Source Station {i + 1}", options=suggestions, format_func=lambda x: x[0] if x else "No suggestions")
            if selected_station:
                source_stations.append(selected_station[1])

    destination_count = st.slider("Number of Destination Stations", min_value=1, max_value=6, value=1)

    destination_stations = []
    cols = st.columns(destination_count)
    for i, col in enumerate(cols):
        destination_input = col.text_input(f"Destination {i + 1}", "")
        if destination_input:
            suggestions = get_station(destination_input)
            selected_station = st.selectbox(f"Select Destination Station {i + 1}", options=suggestions, format_func=lambda x: x[0] if x else "No suggestions")
            if selected_station:
                destination_stations.append(selected_station[1])
    
    col1, col2 = st.columns(2)
    with col1:
        date_option = st.radio("Select search type:", ('Single Day', 'Range of Days'))
    with col2:
        file_format = st.radio("Select file format:", ('Excel', 'CSV'))

    
    if date_option == 'Single Day':
        date_input = st.date_input("Select date of journey:")
        date_range = [date_input.strftime(r'%Y%m%d')]  
    
    else:
        start_date_input = st.date_input("Start date:")
        end_date_input = st.date_input("End date:")

        if start_date_input and end_date_input:
            if start_date_input > end_date_input:
                st.warning("End date must be after start date.")
                return
            else:
                date_range = [(start_date_input + timedelta(days=i)).strftime(r'%Y%m%d') for i in range((end_date_input - start_date_input).days + 1)]
        else:
            st.warning("Please select both start and end dates.")
            return

    if st.button("Check Availability"):
        try:
            all_trains_data = []
            total_iterations = len(source_stations) * len(destination_stations) * len(date_range)
            progress_bar = st.progress(0)  
            current_iteration = 0

            for source_station in source_stations:
                for destination_station in destination_stations:
                    if source_station and destination_station:

                        for date in date_range:
                            try:
                                trains_response = get_trains(source_station, destination_station, date)
                                train_data = extract(trains_response)
                                all_trains_data.extend(train_data)
                            except :
                                human_readable_date = datetime.strptime(date, "%Y%m%d").strftime("%d-%m-%Y")
                                st.warning(f"Error fetching trains for {source_station} to {destination_station} on {human_readable_date}: TrainNotFound")
                                continue
                            finally:
                                current_iteration += 1
                                progress_percentage = current_iteration / total_iterations
                                progress_bar.progress(progress_percentage)  

            progress_bar.empty()  

            if all_trains_data:
                df = pd.DataFrame(sort_train_data(all_trains_data))

                if file_format == 'Excel':
                    excel_data = convert_df_to_excel(df)
                    st.download_button(
                        label="Download Search data as Excel",
                        data=excel_data,
                        file_name=f"{"_".join(source_stations)}_to_{"_".join(destination_stations)}_search.xlsx",
                        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    )
                else:
                    csv_data = convert_df_to_csv(df)
                    st.download_button(
                        label="Download Search data as CSV",
                        data=csv_data,
                        file_name=f"{"_".join(source_stations)}_to_{"_".join(destination_stations)}_search.csv",
                        mime='text/csv'
                    )
            else:
                st.warning("No trains found for the selected inputs.")

        except StationCodeFetchError as e:
            st.error(e)
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")



if __name__ == "__main__":
    main()
