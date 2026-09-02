import re
import unicodedata
import pandas as pd

class CSVTools:

    @staticmethod
    def fix_encoding_text(text: str) -> str:
        """
        Corrige caracteres corrompidos (mojibake) comuns em exportações de NF-e.
        """
        if not isinstance(text, str):
            return text
        try:
            return text.encode('latin1').decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            return text

    @staticmethod
    def clean_column_name(col_name: str) -> str:
        """
        Corrige encoding, remove acentos e converte para minúsculas limpas.
        """
        col_name = CSVTools.fix_encoding_text(str(col_name))
        nfkd_form = unicodedata.normalize('NFKD', col_name)
        only_ascii = nfkd_form.encode('ASCII', 'ignore').decode('utf-8')
        return re.sub(r'[^a-zA-Z0-9]+', '_', only_ascii.lower()).strip('_')

    @classmethod
    def load_csv(cls, file_path: str) -> pd.DataFrame:
        """
        Carrega o CSV resolvendo o erro de UnicodeDecodeError através
        de uma lista de encodings comuns em sistemas fiscais brasileiros.
        """
        encodings_to_try = ['iso-8859-1', 'latin1', 'cp1252', 'utf-8-sig', 'utf-8']
        separators = [',', ';', '\t']
        
        df = None

        for enc in encodings_to_try:
            for sep in separators:
                try:
                    df = pd.read_csv(file_path, encoding=enc, sep=sep, dtype=str)
                    # Verifica se leu mais de 1 coluna (para evitar separador errado)
                    if len(df.columns) > 1:
                        break
                except (UnicodeDecodeError, pd.errors.ParserError):
                    continue
            if df is not None and len(df.columns) > 1:
                break

        if df is None:
            # Fallback final com mecanismo python engine
            try:
                df = pd.read_csv(file_path, encoding='latin1', sep=None, engine='python', dtype=str)
            except Exception as e:
                raise ValueError(f"Não foi possível abrir o arquivo {file_path}: {str(e)}")

        # 1. Padroniza colunas (ex: SÃ‰RIE -> serie, VALOR NOTA FISCAL -> valor_nota_fiscal)
        df.columns = [cls.clean_column_name(col) for col in df.columns]

        # 2. Sanitiza strings do corpo do DataFrame
        for col in df.select_dtypes(include=['object']).columns:
            df[col] = (
                df[col]
                .apply(cls.fix_encoding_text)
                .astype("string")
                .str.strip()
            )

        return df

    @classmethod
    def inspect_csv(cls, file_path: str) -> dict:
        """
        Inspeciona o arquivo e retorna metadados e uma amostra limpa.
        """
        df = cls.load_csv(file_path)

        return {
            "columns": list(df.columns),
            "num_rows": len(df),
            "head": df.head(3).to_dict(orient="records"),
            "dataframe": df
        }