"""
Module to extract type from name
"""

from time import time

import pandas as pd
from flashtext import KeywordProcessor
from preprocessing_pgp.name.accent_typing_formatter import remove_accent_typing
from preprocessing_pgp.name.preprocess import preprocess_df
from preprocessing_pgp.name.type.const import NAME_TYPE_REGEX_DATA
from preprocessing_pgp.utils import parallelize_dataframe


class TypeExtractor:
    """
    Class contains function to support for type extraction from name
    """

    def __init__(self) -> None:
        self.available_levels = NAME_TYPE_REGEX_DATA.keys()
        self.__generate_type_kws()

    def __generate_type_kws(self):
        if hasattr(self, "type_kws"):
            return
        self.type_kws = {}
        for level in self.available_levels:
            level_kws = KeywordProcessor(case_sensitive=True)

            level_kws.add_keywords_from_dict(NAME_TYPE_REGEX_DATA[level])
            self.type_kws[level] = level_kws

    def extract_type(self, name: str, level: str = "lv1") -> str:
        """
        Extract name type from input name

        Parameters
        ----------
        name : str
            The input name to extract type from

        level : str
            The level to search for keyword pattern from,
            by default 'lv1' -- Currently there are 2 level 'lv1' and 'lv2'

        Returns
        -------
        str
            The first type extract from the name
        """
        if not hasattr(self, "type_kws"):
            self.__generate_type_kws()

        results = self.type_kws[level].extract_keywords(name)

        if not results:
            return "customer"
        return results[0]


def format_names(
    data: pd.DataFrame, name_col: str = "name", decode: bool = True
) -> pd.DataFrame:
    """
    Format name with clean and encoded without accent

    Parameters
    ----------
    data : pd.DataFrame
        The input data contains the name records
    name_col : str, optional
        The column name in data holds the name records, by default 'name'

    Returns
    -------
    pd.DataFrame
        Final data contains additional columns:

        * `de_<name_col>` contains decoded & lowered name derived from `name`
    """
    clean_data = data
    if decode:
        clean_data[name_col] = clean_data[name_col].apply(remove_accent_typing)
    clean_data[name_col] = clean_data[name_col].str.lower()

    return clean_data


def extract_ctype(
    data: pd.DataFrame, name_col: str = "de_name", level: str = "lv1"
) -> pd.DataFrame:
    """
    Perform name-type extraction from formatted name col

    Parameters
    ----------
    data : pd.DataFrame
        The original dataframe contains the formatted name col
    name_col : str, optional
        The formatted name col, by default 'de_name'
    level : str, optional
        The level to process type extraction, by default 'lv1'

    Returns
    -------
    pd.DataFrame
        The new data contains additional columns:

        * `customer_type` contains the type of customer extracted from name
    """
    if data.empty:
        return data

    extracted_data = data
    # # ? KWS
    # type_extractor = TypeExtractor()
    # extracted_data['customer_type'] = extracted_data[name_col]\
    #     .apply(
    #         lambda name: type_extractor.extract_type(name, level)
    # )

    # ? Regex
    extracted_data.loc[
        extracted_data[name_col].notna(), "customer_type"
    ] = None

    # * Format lower only
    extracted_data[f"de_{name_col}"] = extracted_data[name_col]
    extracted_data = format_names(
        extracted_data, name_col=f"de_{name_col}", decode=False
    )

    # * Extract customer type accented
    level_name_type_regex = NAME_TYPE_REGEX_DATA[f"{level}_accented"]
    for ctype in level_name_type_regex.keys():
        regex_ctype = "|".join(level_name_type_regex[ctype])
        # Only work with the non-predict type
        ctype_mask = (
            extracted_data[f"de_{name_col}"].str.contains(regex_ctype)
        ) & (extracted_data["customer_type"].isna())
        extracted_data.loc[ctype_mask, "customer_type"] = ctype

    # * Format lower + unidecode
    extracted_data = format_names(
        extracted_data, name_col=f"de_{name_col}", decode=True
    )

    # * Extract customer type accented
    level_name_type_regex = NAME_TYPE_REGEX_DATA[f"{level}_without_accent"]
    for ctype in level_name_type_regex.keys():
        regex_ctype = "|".join(level_name_type_regex[ctype])
        # Only work with the non-predict type
        ctype_mask = (
            extracted_data[f"de_{name_col}"].str.contains(regex_ctype)
        ) & (extracted_data["customer_type"].isna())
        extracted_data.loc[ctype_mask, "customer_type"] = ctype

    # * Fill customer
    extracted_data["customer_type"] = extracted_data["customer_type"].fillna(
        "customer"
    )

    return extracted_data


def process_extract_name_type(
    data: pd.DataFrame,
    name_col: str = "name",
    level: str = "lv1",
    n_cores: int = 1,
    logging_info: bool = True,
) -> pd.DataFrame:
    """
    Extract types from name records inputted from data

    Parameters
    ----------
    data : pd.DataFrame
        The input data contains the name records
    name_col : str, optional
        The column name in data holds the name records, by default 'name'
    level : str, optional
        The level to process type extraction, by default 'lv1'
    n_cores : int
        The number of cores used to run parallel, by default 1 core will be used

    Returns
    -------
    pd.DataFrame
        Final data contains additional columns:

        * `customer_type` contains type of customer extracted from `name` column
    """
    orig_cols = data.columns.difference([name_col])

    # ? Preprocess data
    if logging_info:
        print(">>> Cleansing names: ", end="")
    start_time = time()
    data = parallelize_dataframe(
        data,
        preprocess_df,
        n_cores=n_cores,
        name_col=name_col,
        clean_name=False,
        remove_pronoun=True,
    )
    clean_time = time() - start_time
    if logging_info:
        print(f"{int(clean_time)//60}m{int(clean_time)%60}s")

    # * Remove NaNs and select only name col
    na_data = data[data[name_col].isna()][[name_col]]
    cleaned_data = data[data[name_col].notna()][[name_col]]

    # ? Extract name type by kws
    if logging_info:
        print(">>> Extracting customer's type: ", end="")
    start_time = time()
    # formatted_data = parallelize_dataframe(
    #     cleaned_data,
    #     format_names,
    #     n_cores=n_cores,
    #     name_col=name_col,
    #     decode=False
    # )

    extracted_data = parallelize_dataframe(
        cleaned_data,
        extract_ctype,
        n_cores=n_cores,
        level=level,
        name_col=name_col,
    )
    extract_time = time() - start_time
    if logging_info:
        print(f"{int(extract_time)//60}m{int(extract_time)%60}s")

    # ? Drop clean_name column
    extracted_data = extracted_data.drop(columns=[f"de_{name_col}"])

    # ? Combined with Na data
    new_cols = [name_col, "customer_type"]
    na_data[new_cols] = None
    final_data = pd.concat([extracted_data, na_data])

    # ? Combined with the origin cols
    final_data = pd.concat([data[orig_cols], final_data[new_cols]], axis=1)

    return final_data
