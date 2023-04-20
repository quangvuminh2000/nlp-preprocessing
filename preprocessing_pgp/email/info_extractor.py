"""
Module contains objects and functions to support extracting information from email
"""

from time import time

import pandas as pd
from preprocessing_pgp.email.extractors.email_address_extractor import (
    EmailAddressExtractor,
)
from preprocessing_pgp.email.extractors.email_name_extractor import (
    EmailNameExtractor,
)
from preprocessing_pgp.email.extractors.email_phone_extractor import (
    EmailPhoneExtractor,
)
from preprocessing_pgp.email.extractors.email_yob_extractor import (
    EmailYOBExtractor,
)
from preprocessing_pgp.email.validator import process_validate_email
from preprocessing_pgp.name.enrich_name import process_enrich
from preprocessing_pgp.name.gender.predict_gender import process_predict_gender
from preprocessing_pgp.utils import parallelize_dataframe


class EmailInfoExtractor:
    """
    Class contains function to extract for email information
    """

    def __init__(self):
        # Using factory pattern for better view
        self.name_extractor = EmailNameExtractor()
        self.yob_extractor = EmailYOBExtractor()
        self.phone_extractor = EmailPhoneExtractor()
        self.address_extractor = EmailAddressExtractor()

    def enrich_extracted_email_name(
        self,
        data: pd.DataFrame,
        email_name_col: str = "email_name",
        ctype_col: str = "customer_type",
    ) -> pd.DataFrame:
        """
        Process enrich for extracted email name
        """
        extracted_data = data
        orig_cols = data.columns

        proceed_mask = (extracted_data[email_name_col].notna()) & (
            extracted_data[ctype_col] == "customer"
        )
        proceed_data = extracted_data[proceed_mask]
        ignored_data = extracted_data[~proceed_mask]

        # * Enrich name
        proceed_data.drop(columns=["customer_type"], inplace=True)
        proceed_data = process_enrich(
            proceed_data,
            name_col=email_name_col,
            n_cores=1,
            logging_info=False,
        )

        # * Predict gender from extracted username
        proceed_data = process_predict_gender(
            proceed_data, name_col="final", n_cores=1, logging_info=False
        )

        # * Re-ordering
        proceed_data.rename(
            columns={
                "gender_predict": "gender_extracted",
                "final": "enrich_name",
            },
            inplace=True,
        )

        final_data = pd.concat([proceed_data, ignored_data])

        return final_data[
            [
                *orig_cols,
                # f'cleaned_{email_name_col}',
                # 'customer_type',
                # 'username_extracted',
                "enrich_name",
                "gender_extracted",
                "gender_score",
            ]
        ]

    def extract_info(
        self, data: pd.DataFrame, email_name_col: str = "email_name"
    ) -> pd.DataFrame:
        """
        Extract any information from email's name if possible

        Parameters
        ----------
        data : pd.DataFrame
            The input data contains an email_name column
        email_name_col : str, optional
            The name of the column contains email's name, by default 'email_name'

        Returns
        -------
        pd.DataFrame
            Data with additional info columns:
            * `username_extracted` : Extracted username from email name
            * `gender_extracted` : Extracted gender from username
            * `yob_extracted` : Extracted year of birth from email name
            * `phone_extracted` : Extracted phone number from email name
            * `address_extracted` : Extracted address from email name
        """
        if data.empty:
            return data
        # * Extracting name & gender
        extracted_data = self.name_extractor.extract_username(
            data, email_name_col
        )
        extracted_data = self.enrich_extracted_email_name(
            extracted_data,
            email_name_col="username_extracted",
            ctype_col="customer_type",
        )

        # * Extracting yob
        extracted_data = self.yob_extractor.extract_yob(
            extracted_data, email_name_col
        )

        # * Extracting phone
        extracted_data = self.phone_extractor.extract_phone(
            extracted_data, email_name_col
        )

        # * Extracting address
        extracted_city_mask = extracted_data["enrich_name"].isna()
        extracted_data["address_extracted"] = None
        extracted_data[
            extracted_city_mask
        ] = self.address_extractor.extract_address(
            extracted_data[extracted_city_mask], email_name_col
        )

        return extracted_data


def process_extract_email_info(
    data: pd.DataFrame,
    email_col: str = "email",
    n_cores: int = 1,
    domain_dict: pd.DataFrame = None,
) -> pd.DataFrame:
    """
    Process extracting information from email, extracted information may conclude:
    1. Username -- with accent
    2. Customer type -- derived from username
    3. Year of birth
    4. Address -- 3 levels
    5. Email group
    6. Auto-email

    Parameters
    ----------
    data : pd.DataFrame
        The input data contains an email column
    email_col : str
        The name of the column contains email's records, by default `email`
    n_cores : int
        The number of core to process

    Returns
    -------
    pd.DataFrame
        Original data with additional columns contains 6 additional information as above
    """

    # * Select the part of data to process
    email_data = data[[email_col]]
    orig_cols = data.columns

    info_extractor = EmailInfoExtractor()
    # ? Validate email -- Only extract info for valid email
    validated_data = process_validate_email(
        email_data,
        email_col=email_col,
        n_cores=n_cores,
        domain_dict=domain_dict,
    )
    valid_email = validated_data.query("is_email_valid")
    invalid_email = validated_data.query("~is_email_valid")

    if valid_email.empty:
        return invalid_email
    # ? Separate email name and group
    valid_email[f"{email_col}_name"] = (
        valid_email[f"cleaned_{email_col}"].str.split("@").str[0]
    )

    # ? Extract username from email
    start_time = time()
    extracted_valid_email = parallelize_dataframe(
        valid_email,
        info_extractor.extract_info,
        n_cores=n_cores,
        email_name_col=f"{email_col}_name",
    )
    extract_time = time() - start_time
    print(">>> Extracting information from email: ", end="")
    print(f"{int(extract_time)//60}m{int(extract_time)%60}s")

    if invalid_email.empty:
        final_data = extracted_valid_email
    else:
        final_data = pd.concat([extracted_valid_email, invalid_email])

    # * Generate whether username is certain
    final_data["username_iscertain"] = (final_data["is_email_valid"]) & (
        final_data["customer_type"] == "customer"
    )

    # * Concat with data of other columns
    extracted_cols = [
        f"{email_col}_name",
        f"cleaned_{email_col}",
        "is_email_valid",
        "is_autoemail",
        "username_iscertain",
        "email_domain",
        "private_email",
        "customer_type",
        "username_extracted",
        "enrich_name",
        "gender_extracted",
        "yob_extracted",
        "phone_extracted",
        "address_extracted",
    ]
    final_data = pd.concat(
        [data[orig_cols], final_data[extracted_cols]], axis=1
    )

    return final_data
