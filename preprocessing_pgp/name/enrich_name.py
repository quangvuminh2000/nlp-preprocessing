import json
import logging
import warnings
from time import time
from typing import Tuple

import pandas as pd
from preprocessing_pgp.name.const import MODEL_PATH, RULE_BASED_PATH
from preprocessing_pgp.name.model.transformers import TransformerModel

# from preprocessing_pgp.email.extractors.email_name_extractor import EmailNameExtractor
from preprocessing_pgp.name.name_processing import NameProcessor
from preprocessing_pgp.name.preprocess import get_name_pronoun, preprocess_df
from preprocessing_pgp.name.split_name import NameProcess
from preprocessing_pgp.name.type.extractor import process_extract_name_type
from preprocessing_pgp.utils import (  # sep_display,
    parallelize_dataframe,
    replace_trash_string,
)
from tensorflow import keras
from tqdm import tqdm

tqdm.pandas()
warnings.filterwarnings("ignore")
logger = logging.getLogger()
logger.setLevel(logging.CRITICAL)


class EnrichName:
    """
    Wrap-up module to enrich and filling accent to names
    """

    def __init__(
        self,
        model_weight_path: str,
        vectorization_paths: Tuple[str, str],
        model_config_path: str,
        name_rb_pth: str,
    ) -> None:
        start_time = time()
        self.model = self.load_model(
            model_weight_path, vectorization_paths, model_config_path
        )
        self.fname_rb = f"{name_rb_pth}/firstname_dict.parquet"
        self.mname_rb = f"{name_rb_pth}/middlename_dict.parquet"
        self.lname_rb = f"{name_rb_pth}/lastname_dict.parquet"
        self.name_processor = NameProcessor(
            self.model,
            self.fname_rb,
            self.mname_rb,
            self.lname_rb,
        )
        # Timing
        self.total_load_time = time() - start_time

    def load_model(
        self,
        model_weight_path: str,
        vectorization_paths: Tuple[str, str],
        model_config_path: str,
    ) -> TransformerModel:
        start_time = time()
        # ? Load config dict
        with open(model_config_path) as json_file:
            config_dict = json.load(json_file)

        # ? BUILD & LOAD MODEL
        source_vec_pth, target_vec_pth = vectorization_paths
        transformer = TransformerModel(
            source_vectorization=source_vec_pth,
            target_vectorization=target_vec_pth,
            config_dict=config_dict,
        )
        transformer.build_model(
            optimizer=keras.optimizers.Adam(
                learning_rate=config_dict["LEARNING_RATE"]
            ),
            loss="sparse_categorical_crossentropy",
            metrics=["accuracy"],
        )
        transformer.load_model_weights(model_weight_path)

        self.model_load_time = time() - start_time

        return transformer

    def refill_accent(
        self, name_df: pd.DataFrame, name_col: str
    ) -> pd.DataFrame:
        return self.name_processor.fill_accent(name_df, name_col)

    def get_time_report(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "model load time": [self.model_load_time],
                "total load time": [self.total_load_time],
            }
        )


def enrich_clean_data(
    clean_df: pd.DataFrame,
    name_col: str,
) -> pd.DataFrame:
    """
    Applying the model of filling accent to cleaned Vietnamese names

    Parameters
    ----------
    clean_df : pd.DataFrame
        The dataframe containing cleaned names
    name_col : str
        The column name that holds the raw names

    Returns
    -------
    pd.DataFrame
        The final dataframe that contains:

        * `name_col`: raw names -- input name column
        * `predict`: predicted names using model only
        * `final`: beautified version of prediction with additional rule-based approach
    """
    if clean_df.empty:
        return clean_df
    model_weight_path = f"{MODEL_PATH}/best_transformer_model.h5"
    vectorization_paths = (
        f"{MODEL_PATH}/vecs/source_vectorization_layer.pkl",
        f"{MODEL_PATH}/vecs/target_vectorization_layer.pkl",
    )
    model_config_path = f"{MODEL_PATH}/hp.json"

    enricher = EnrichName(
        model_weight_path=model_weight_path,
        vectorization_paths=vectorization_paths,
        model_config_path=model_config_path,
        name_rb_pth=RULE_BASED_PATH,
    )

    final_df = enricher.refill_accent(clean_df, name_col)

    return final_df


def prepare_name(
    data: pd.DataFrame,
    name_col: str = "name",
    n_cores: int = 1,
    logging_info: bool = True,
) -> pd.DataFrame:
    """
    Preparation module for name data

    Parameters
    ----------
    data : pd.DataFrame
    name_col : str, optional
        by default 'name'
    n_cores : int, optional
        by default 1
    logging_info : bool, optional
        by default True

    Returns
    -------
    pd.DataFrame
    """
    orig_cols = data.columns.difference([name_col])
    # * Na names & filter out name col
    na_data = data[data[name_col].isna()][[name_col]]
    cleaned_data = data[data[name_col].notna()][[name_col]]

    # * Clean name without remove pronoun, dot
    cleaned_data = parallelize_dataframe(
        cleaned_data,
        preprocess_df,
        n_cores=n_cores,
        name_col=name_col,
        clean_name=False,
        remove_pronoun=False,
        exclude_dot=True,
    )

    # * Split pronoun
    cleaned_data["pronoun"] = cleaned_data[name_col].apply(get_name_pronoun)

    # * Clean name without remove pronoun
    cleaned_data = parallelize_dataframe(
        cleaned_data,
        preprocess_df,
        n_cores=n_cores,
        name_col=name_col,
        clean_name=False,
        remove_pronoun=True,
    )

    # * Extracting customer type -- Only enrich 'customer' type
    cleaned_data = process_extract_name_type(
        cleaned_data, name_col, n_cores=n_cores, logging_info=logging_info
    )

    # * Concat with original cols
    final_data = pd.concat([na_data, cleaned_data])
    final_data = pd.concat([data[orig_cols], final_data[[name_col]]], axis=1)

    return final_data


def process_enrich(
    data: pd.DataFrame,
    name_col: str = "name",
    n_cores: int = 1,
    logging_info: bool = True,
    process_customer_type: bool = True,
) -> pd.DataFrame:
    """
    Applying the model of filling accent to non-accent Vietnamese names
    received from the `raw_df` at `name_col` column.

    Parameters
    ----------
    data : pd.DataFrame
        The dataframe containing raw names
    name_col : str
        The column name that holds the raw names, by default 'name'
    n_cores : int
        The number of cores used to run parallel, by default 1 core is used
    logging_info : bool
        Whether to log info about run time, by default True
    skip_customer_type : bool
        Whether to log info about run time, by default True

    Returns
    -------
    pd.DataFrame
        The final dataframe that contains:

        * `customer_type`: the type of customer extracted from name
        * `predict`: predicted names using model only
        * `final`: beautified version of prediction with additional rule-based approach
    """
    orig_cols = data.columns

    # * Na names & filter out name col
    na_data = data[data[name_col].isna()][[name_col]]
    cleaned_data = data[data[name_col].notna()][[name_col]]

    # * Clean name without remove pronoun, dot
    cleaned_data = parallelize_dataframe(
        cleaned_data,
        preprocess_df,
        n_cores=n_cores,
        name_col=name_col,
        clean_name=False,
        remove_pronoun=False,
        exclude_dot=True,
    )

    # * Split pronoun
    cleaned_data["pronoun"] = cleaned_data[name_col].apply(get_name_pronoun)

    # * Clean name without remove pronoun
    cleaned_data = parallelize_dataframe(
        cleaned_data,
        preprocess_df,
        n_cores=n_cores,
        name_col=name_col,
        clean_name=False,
        remove_pronoun=True,
    )

    # * Extracting customer type -- Only enrich 'customer' type
    if process_customer_type:
        cleaned_data = process_extract_name_type(
            cleaned_data, name_col, n_cores=n_cores, logging_info=logging_info
        )
        customer_data = cleaned_data.query('customer_type == "customer"')
        #                    | (cleaned_data[name_col].str.split(' ').str.len() > 3))
        non_customer_data = cleaned_data.query('customer_type != "customer"')
    else:
        customer_data = cleaned_data
        customer_data["customer_type"] = "customer"
        non_customer_data = pd.DataFrame()

    # # Clean names -- Not Needed
    # start_time = time()
    # if n_cores == 1:
    #     customer_data = preprocess_df(
    #         customer_data,
    #         name_col=name_col
    #     )
    # else:
    #     customer_data = parallelize_dataframe(
    #         customer_data,
    #         preprocess_df,
    #         n_cores=n_cores,
    #         name_col=name_col
    #     )
    # clean_time = time() - start_time
    # print(f"Cleansing takes {int(clean_time)//60}m{int(clean_time)%60}s")
    # sep_display()

    # Enrich names
    if logging_info:
        print(">>> Enriching names")
    start_time = time()
    enriched_data = parallelize_dataframe(
        customer_data, enrich_clean_data, n_cores=n_cores, name_col=name_col
    )
    enrich_time = time() - start_time
    if logging_info:
        print(f"Time elapsed: {int(enrich_time)//60}m{int(enrich_time)%60}s")

    if logging_info:
        print(">>> Enrich glue names")
    start_time = time()

    # name_extractor = EmailNameExtractor()
    name_process = NameProcess()
    # non_glue_names = enriched_data[enriched_data['final'].notna()]
    # glue_names = enriched_data[enriched_data['final'].isna()]

    # if not glue_names.empty:
    #     glue_names[name_col] = glue_names[name_col]\
    #         .str.lower()\
    #         .apply(unidecode)

    #     glue_multi_names = glue_names[glue_names[name_col].str.split(
    #     ).str.len() > 1]
    #     glue_single_names = glue_names[glue_names[name_col].str.split(
    #     ).str.len() <= 1]

    #     glue_single_names = parallelize_dataframe(
    #         glue_single_names[[name_col]],
    #         name_extractor.extract_username,
    #         n_cores=n_cores,
    #         email_name_col=name_col
    #     )\
    #         .drop(columns=[name_col])\
    #         .rename(columns={
    #             'username_extracted': name_col
    #         })

    #     glue_single_names = parallelize_dataframe(
    #         glue_single_names[[name_col]],
    #         enrich_clean_data,
    #         n_cores=n_cores,
    #         name_col=name_col
    #     )

    #     glue_single_names['predict'] = glue_single_names['final']
    #     glue_single_names[['last_name', 'middle_name', 'first_name']] =\
    #         glue_single_names['final'].apply(
    #             name_process.SplitName
    #     ).tolist()

    #     glue_multi_names = parallelize_dataframe(
    #         glue_multi_names,
    #         enrich_clean_data,
    #         n_cores=n_cores,
    #         name_col=name_col
    #     )

    #     if glue_multi_names.empty:
    #         glue_names= glue_multi_names
    #     else:
    #         glue_names = pd.concat([
    #             glue_multi_names,
    #             glue_single_names
    #         ])

    #     glue_name_time = time() - start_time
    #     if logging_info:
    #         print(
    #             f"Time elapsed: {int(glue_name_time)//60}m{int(glue_name_time)%60}s")

    # * Concat na data
    new_cols = [
        f"clean_{name_col}",
        "customer_type",
        "predict",
        "final",
        "last_name",
        "middle_name",
        "first_name",
        "pronoun",
    ]
    na_data[new_cols] = None
    final_data = pd.concat(
        [
            # non_glue_names,
            # glue_names,
            enriched_data,
            non_customer_data,
            na_data,
        ]
    )

    final_data.loc[final_data["final"].notna(), "n_words"] = (
        final_data["final"].str.split().str.len()
    )

    final_data.loc[final_data["final"].notna(), "name_len"] = (
        final_data["final"].str.replace(r"\s+", "", regex=True).str.len()
    )

    final_data.loc[
        ~(
            (
                final_data["n_words"].isin([2, 3, 4, 5])
                & (final_data["name_len"] >= 4)
                & (final_data["name_len"] <= 30)
            )
            | (
                final_data["n_words"].isin([1])
                & (final_data["name_len"] >= 2)
                & (final_data["name_len"] <= 6)
            )
        ),
        "final",
    ] = None

    # * Extract name element
    final_data[["last_name", "middle_name", "first_name"]] = (
        final_data["final"].apply(name_process.SplitName).tolist()
    )

    final_data["final"] = (
        final_data[["last_name", "middle_name", "first_name"]]
        .fillna("")
        .agg(" ".join, axis=1)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

    final_data["final"] = replace_trash_string(final_data, "final")

    # * Transform to same name format
    name_ele_cols = [
        f"clean_{name_col}",
        "predict",
        "final",
        "last_name",
        "middle_name",
        "first_name",
    ]

    for col in name_ele_cols:
        final_data[col] = final_data[col].str.lower()

    # * Concat with original cols
    final_data = pd.concat([data[orig_cols], final_data[new_cols]], axis=1)

    return final_data
