"""
File containing logic to extract a full address into 3 levels:

* Level 1: City, Countryside
* Level 2: District
* Level 3: Ward
"""
from time import time

import pandas as pd
from preprocessing_pgp.address.const import AVAIL_LEVELS
from preprocessing_pgp.address.level_extractor import (
    extract_vi_address_by_level,
)
from preprocessing_pgp.address.loc_process import generate_loc_code
from preprocessing_pgp.address.preprocess import clean_vi_address
from preprocessing_pgp.utils import extract_null_values, parallelize_dataframe


def extract_vi_address(
    data: pd.DataFrame,
    address_col: str,
    n_cores: int = 1,
    logging_info: bool = True,
) -> pd.DataFrame:
    """
    Extract Vietnamese address by pattern to find 3 levels of address

    Parameters
    ----------
    data : pd.DataFrame
        The input raw data with address column
    address_col : str
        The name of the column containing addresses
    n_cores : int, optional
        The number of cores used to run parallel, by default 1 core will be used

    Returns
    -------
    pd.DataFrame
        The data with additional columns:

        * `cleaned_<address_col>` contains the unified and clean Vietnamese address
        * `level_1`: city, countryside found
        * `best_level_1`: beautified city, countryside found
        * `level_1_code`: code for city
        * `level_2`: district found
        * `best_level_2`: beautified district found
        * `level_2_code`: code for district
        * `level_3`: ward found
        * `best_level_3`: beautified ward found
        * `level_3_code`: code for ward
        * `remained address`: the remaining in the address
    """

    # * Select only address column
    orig_cols = data.columns
    address_data = data[[address_col]]

    # * Removing na addresses
    clean_address_data, na_address_data = extract_null_values(
        address_data, by_col=address_col
    )

    # * Cleanse the address
    if logging_info:
        print(">>> Cleansing address: ", end="")
    start_time = time()
    cleaned_data = parallelize_dataframe(
        clean_address_data,
        clean_vi_address,
        n_cores=n_cores,
        address_col=address_col,
    )
    clean_time = time() - start_time
    if logging_info:
        print(f"{int(clean_time)//60}m{int(clean_time)%60}s")

    # * Feed the cleansed address to extract the level
    if logging_info:
        print(">>> Extract & Beautify address: ", end="")
    start_time = time()
    extracted_data = parallelize_dataframe(
        cleaned_data,
        extract_vi_address_by_level,
        n_cores=n_cores,
        address_col=f"cleaned_{address_col}",
    )
    extract_time = time() - start_time
    if logging_info:
        print(f"{int(extract_time)//60}m{int(extract_time)%60}s")

    # * Generate location code for best level found
    if logging_info:
        print(">>> Generating address code: ", end="")
    start_time = time()
    best_lvl_cols = [f"best_level_{i}" for i in AVAIL_LEVELS]
    generated_data = parallelize_dataframe(
        extracted_data,
        generate_loc_code,
        n_cores=n_cores,
        best_lvl_cols=best_lvl_cols,
    )
    code_gen_time = time() - start_time
    if logging_info:
        print(f"{int(code_gen_time)//60}m{int(code_gen_time)%60}s")

    # * Concat to original data
    final_data = pd.concat([generated_data, na_address_data])

    # * Concat with origin columns
    new_cols = [
        "level_1",
        "best_level_1",
        "level_1_code",
        "level_2",
        "best_level_2",
        "level_2_code",
        "level_3",
        "best_level_3",
        "level_3_code",
        "remained_address",
    ]
    final_data = pd.concat([data[orig_cols], final_data[new_cols]], axis=1)

    return final_data
