
import pandas as pd
import numpy as np
from unidecode import unidecode
from datetime import datetime, timedelta
import sys

import subprocess
from pyarrow import fs

sys.path.append('/bigdata/fdp/cdp/source/core_profile/preprocess/utils')
from preprocess_profile import (
    remove_same_username_email,
    extracting_pronoun_from_name
)
from enhance_profile import enhance_common_profile
from filter_profile import get_difference_data
from const import (
    hdfs,
    UTILS_PATH,
    CENTRALIZE_PATH,
    PREPROCESS_PATH
)

# function get profile change/new


# def DifferenceProfile(now_df, yesterday_df):
#     difference_df = now_df[~now_df.apply(tuple, 1).isin(
#         yesterday_df.apply(tuple, 1))].copy()
#     return difference_df

# function unify profile


def UnifyFo(
    profile_vne: pd.DataFrame,
    n_cores: int = 1
):
    #* Sorting by uid --> Remove duplicated uid
    print(">>> Processing Info")
    profile_vne = profile_vne.sort_values(
        by=['uid'], ascending=False)
    profile_vne = profile_vne.drop_duplicates(subset=['uid'], keep='first')

    # * Enhancing common profile
    profile_vne = enhance_common_profile(
        profile_vne,
        n_cores=n_cores
    )

    # birthday
    print(">>> Processing Birthday")
    now_year = datetime.today().year
    profile_vne.loc[profile_vne['age'] < 0, 'age'] = np.nan
    # profile_fo.loc[profile_fo['age'] > profile_fo['age'].quantile(0.99), 'age'] = np.nan
    profile_vne.loc[profile_vne['age'] > 72, 'age'] = np.nan
    profile_vne.loc[profile_vne['age'].notna(), 'birthday'] =\
        (now_year - profile_vne[profile_vne['age'].notna()]['age'])\
        .astype(str).str.replace('.0', '', regex=False)
    profile_vne = profile_vne.drop(columns=['age'])
    profile_vne.loc[profile_vne['birthday'].isna(), 'birthday'] = None

    # gender
    print(">>> Processing Gender")
    profile_vne['gender'] = profile_vne['gender'].replace(
        {'Female': 'F', 'Male': 'M', 'Other': None})

    # drop name is username_email
    print(">>> Extra Cleansing Name")
    profile_vne = remove_same_username_email(
        profile_vne,
        name_col='name',
        email_col='email'
    )
    # profile_fo['username_email'] = profile_fo['email'].str.split('@').str[0]
    # profile_fo.loc[profile_fo['name'] ==
    #                profile_fo['username_email'], 'name'] = None
    # profile_fo = profile_fo.drop(columns=['username_email'])

    # clean name, extract pronoun

    condition_name = (profile_vne['customer_type'] == 'Ca nhan')\
        & (profile_vne['name'].notna())
    profile_vne = extracting_pronoun_from_name(
        profile_vne,
        condition_name,
        name_col='name',
    )

    # name_process = NameProcess()
    # profile_fo.loc[
    #     condition_name,
    #     ['clean_name', 'pronoun']
    # ] = profile_fo.loc[condition_name, 'name']\
    #     .apply(name_process.CleanName).tolist()

    # profile_fo.loc[
    #     profile_fo['customer_type'] == 'customer',
    #     'name'
    # ] = profile_fo['clean_name']
    # profile_fo = profile_fo.drop(columns=['clean_name'])

    # is full name
    print(">>> Checking Full Name")
    profile_vne.loc[profile_vne['last_name'].notna(
    ) & profile_vne['first_name'].notna(), 'is_full_name'] = True
    profile_vne['is_full_name'] = profile_vne['is_full_name'].fillna(False)
    profile_vne = profile_vne.drop(
        columns=['last_name', 'middle_name', 'first_name'])

    # valid gender by model
    print(">>> Validating Gender")
    profile_vne.loc[
        profile_vne['customer_type'] != 'Ca nhan',
        'gender'
    ] = None
    # profile_fo.loc[profile_fo['gender'].notna() & profile_fo['name'].isna(), 'gender'] = None
    profile_vne.loc[
        (profile_vne['gender'].notna())
        & (profile_vne['gender'] != profile_vne['gender_enrich']),
        'gender'
    ] = None

    # address, city
    print(">>> Processing Address")
    norm_fo_city = pd.read_parquet('/data/fpt/ftel/cads/dep_solution/user/namdp11/scross_fill/runner/refactor/material/ftel_provinces.parquet',
                                   filesystem=hdfs)
    norm_fo_city.columns = ['city', 'norm_city']
    profile_vne.loc[profile_vne['address'] == 'Not set', 'address'] = None
    profile_vne.loc[profile_vne['address'].notna(
    ), 'city'] = profile_vne.loc[profile_vne['address'].notna(), 'address'].apply(unidecode)
    profile_vne['city'] = profile_vne['city'].replace({
        'Ba Ria - Vung Tau': 'Vung Tau',
        'Thua Thien Hue': 'Hue',
        'Bac Kan': 'Bac Can',
        'Dak Nong': 'Dac Nong'
    })
    profile_vne = pd.merge(
        profile_vne.set_index('city'),
        norm_fo_city.set_index('city'),
        left_index=True, right_index=True,
        how='left',
        sort=False
    ).reset_index()
    profile_vne['city'] = profile_vne['norm_city']
    profile_vne = profile_vne.drop(columns=['norm_city'])
    profile_vne.loc[profile_vne['city'].isna(), 'city'] = None
    profile_vne['address'] = None

    # add info
    print(">>> Adding Temp Info")
    profile_vne['unit_address'] = None
    profile_vne['ward'] = None
    profile_vne['district'] = None
    columns = ['uid', 'phone_raw', 'phone', 'is_phone_valid',
               'email_raw', 'email', 'is_email_valid',
               'name', 'pronoun', 'is_full_name', 'gender',
               'birthday', 'customer_type',  # 'customer_type_detail',
               'address', 'unit_address', 'ward', 'district', 'city']
    profile_vne = profile_vne[columns]

    # Fill customer type 'Ca nhan'
    profile_vne.loc[
        (profile_vne['name'].notna())
        & (profile_vne['customer_type'].isna()),
        'customer_type'
    ] = 'Ca nhan'

    # return
    return profile_vne

# function update profile (unify)


def UpdateUnifyFo(
    now_str:str,
    n_cores:int = 1
):
    # VARIABLES
    f_group = 'fo_vne'
    yesterday_str = (datetime.strptime(now_str, '%Y-%m-%d') -
                     timedelta(days=1)).strftime('%Y-%m-%d')

    # load profile (yesterday, now)
    print(">>> Loading today and yesterday profile")
    info_columns = ['uid', 'phone', 'email', 'name',
                    'gender', 'age', 'address']
    now_profile = pd.read_parquet(
        f'{CENTRALIZE_PATH}/{f_group}.parquet/d={now_str}',
        filesystem=hdfs, columns=info_columns
    )
    yesterday_profile = pd.read_parquet(
        f'{CENTRALIZE_PATH}/{f_group}.parquet/d={yesterday_str}',
        filesystem=hdfs, columns=info_columns
    )

    # get profile change/new
    print(">>> Filtering new profile")
    difference_profile = get_difference_data(now_profile, yesterday_profile)
    print(f"Number of new profile {difference_profile.shape}")

    # update profile
    profile_unify = pd.read_parquet(
        f'{PREPROCESS_PATH}/{f_group}.parquet/d={yesterday_str}',
        filesystem=hdfs
    )
    if not difference_profile.empty:
        # get profile unify (old + new)
        new_profile_unify = UnifyFo(difference_profile, n_cores=n_cores)

        # synthetic profile
        profile_unify = pd.concat(
            [new_profile_unify, profile_unify],
            ignore_index=True
        )

    # arrange columns
    print(">>> Re-Arranging Columns")
    columns = [
        'uid', 'phone_raw', 'phone', 'is_phone_valid',
        'email_raw', 'email', 'is_email_valid',
        'name', 'pronoun', 'is_full_name', 'gender',
        'birthday', 'customer_type',  # 'customer_type_detail',
        'address', 'unit_address', 'ward', 'district', 'city'
    ]
    profile_unify = profile_unify[columns]
    profile_unify['is_phone_valid'] =\
        profile_unify['is_phone_valid'].fillna(False)
    profile_unify['is_email_valid'] =\
        profile_unify['is_email_valid'].fillna(False)
    profile_unify = profile_unify.drop_duplicates(
        subset=['uid', 'phone_raw', 'email_raw'],
        keep='first'
    )

    # Type casting for saving
    print(">>> Process casting columns...")
    profile_unify['uid'] = profile_unify['uid'].astype(str)
    profile_unify['birthday'] = profile_unify['birthday'].astype('datetime64[s]')

    # save
    print(f'Checking {f_group} data for {now_str}...')
    f_group_path = f'{PREPROCESS_PATH}/{f_group}.parquet'
    proc = subprocess.Popen(['hdfs', 'dfs', '-test', '-e', f_group_path + f'/d={now_str}'])
    proc.communicate()
    if proc.returncode == 0:
        print("Data already existed, Removing...")
        subprocess.run(['hdfs', 'dfs', '-rm', '-r', f_group_path + f'/d={now_str}'])

    profile_unify['d'] = now_str
    profile_unify.to_parquet(
        f_group_path,
        filesystem=hdfs, index=False,
        partition_cols='d',
        coerce_timestamps='us',
        allow_truncated_timestamps=True
    )
# function update ip (most)


def UnifyLocationIpFo():
    # MOST LOCATION IP
    dict_ip_path = '/data/fpt/ftel/cads/dep_solution/user/namdp11/scross_fill/runner/ip/dictionary'
    log_ip_path = '/data/fpt/ftel/cads/dep_solution/user/namdp11/scross_fill/runner/ip/fo'

    ip_location1 = pd.read_parquet(
        f'{dict_ip_path}/ip_location_batch_1.parquet', filesystem=hdfs)
    ip_location2 = pd.read_parquet(
        f'{dict_ip_path}/ip_location_batch_2.parquet', filesystem=hdfs)
    ip_location = pd.concat([ip_location1, ip_location2], ignore_index=True)
    # ip_location = ip_location1.append(ip_location2, ignore_index=True)
    ip_location = ip_location[['ip', 'name_province', 'name_district']]

    # update ip
    def IpFo(date):
        date_str = date.strftime('%Y-%m-%d')
        try:
            # load log ip
            log_df = pd.read_parquet(f"/data/fpt/fdp/fo/dwh/stag_access_features.parquet/d={date_str}",
                                     filesystem=hdfs, columns=['user_id', 'ip', 'isp']).drop_duplicates()
            log_df['date'] = date_str
            log_df.to_parquet(
                f'{log_ip_path}/ip_{date_str}.parquet', index=False, filesystem=hdfs)

            # add location
            location_df =\
                pd.merge(
                    log_df.set_index('ip'),
                    ip_location.set_index('ip'),
                    how='left',
                    left_index=True,
                    right_index=True
                ).reset_index()
            # log_df.merge(ip_location, how='left', on='ip')
            location_df.to_parquet(
                f'{log_ip_path}/location/ip_{date_str}.parquet', index=False, filesystem=hdfs)
        except:
            print('IP-FO Fail: {}'.format(date_str))

    start_date = sorted([f.path
                         for f in hdfs.get_file_info(fs.FileSelector(log_ip_path))
                         ])[-2][-18:-8]
    end_date = (datetime.today() - timedelta(days=1)).strftime('%Y-%m-%d')
    dates = pd.date_range(start_date, end_date, freq='D')

    for date in dates:
        IpFo(date)

    # stats location ip
    logs_ip_path = sorted([f.path for f in hdfs.get_file_info(
        fs.FileSelector(f'{log_ip_path}/location/'))])[-180:]
    ip_fo = pd.read_parquet(logs_ip_path, filesystem=hdfs)
    stats_ip_fo = ip_fo.groupby(by=['user_id', 'name_province', 'name_district'])[
        'date'].agg(num_date='count').reset_index()
    stats_ip_fo = stats_ip_fo.sort_values(
        by=['user_id', 'num_date'], ascending=False)
    most_ip_fo = stats_ip_fo.drop_duplicates(subset=['user_id'], keep='first')
    most_ip_fo.to_parquet(
        f'{UTILS_PATH}/fo_location_most.parquet',
        index=False, filesystem=hdfs
    )


if __name__ == '__main__':

    TODAY = sys.argv[1]
    UpdateUnifyFo(TODAY, n_cores=5)
    UnifyLocationIpFo()
