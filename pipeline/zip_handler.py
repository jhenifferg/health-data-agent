from pathlib import Path, PureWindowsPath
import stat
from zipfile import ZipFile


class UnsafeZipEntryError(ValueError):
    pass


class ZipLimitExceededError(ValueError):
    pass


class ZipHandler:
    """Extrai ZIPs sob limites e dentro de um diretório reservado."""

    @staticmethod
    def extract(
        zip_path: str,
        output_dir: str,
        *,
        max_members: int = 1000,
        max_member_bytes: int = 500 * 1024 * 1024,
        max_uncompressed_bytes: int = 1024 * 1024 * 1024,
    ) -> list[str]:
        zip_file = Path(zip_path)
        destination = Path(output_dir)

        if not zip_file.exists():
            raise FileNotFoundError(f"Arquivo ZIP nao encontrado: {zip_path}")

        destination.mkdir(parents=True, exist_ok=True)
        destination_root = destination.resolve()
        extracted_files: list[str] = []

        with ZipFile(zip_file, "r") as archive:
            members = archive.infolist()
            if len(members) > max_members:
                raise ZipLimitExceededError("O ZIP excede o número máximo de entradas")

            validated: list[tuple[object, Path]] = []
            seen_paths: set[str] = set()
            total_size = 0
            for member in members:
                normalized_name = member.filename.replace("\\", "/")
                if (
                    normalized_name.startswith("__MACOSX/")
                    or Path(normalized_name).name.startswith("._")
                    or Path(normalized_name).name == ".DS_Store"
                ):
                    continue
                member_path = Path(normalized_name)
                windows_path = PureWindowsPath(normalized_name)
                if (
                    not normalized_name
                    or member_path.is_absolute()
                    or windows_path.is_absolute()
                    or windows_path.drive
                    or ".." in member_path.parts
                ):
                    raise UnsafeZipEntryError(
                        f"Entrada ZIP insegura: {member.filename}"
                    )

                mode = (member.external_attr >> 16) & 0xFFFF
                file_type = stat.S_IFMT(mode)
                if file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise UnsafeZipEntryError(
                        f"Tipo de entrada ZIP não permitido: {member.filename}"
                    )

                target = (destination / member_path).resolve()
                if target != destination_root and destination_root not in target.parents:
                    raise UnsafeZipEntryError(
                        f"Entrada ZIP fora do diretório reservado: {member.filename}"
                    )

                path_key = target.relative_to(destination_root).as_posix()
                if path_key in seen_paths:
                    raise UnsafeZipEntryError(
                        f"Entrada ZIP duplicada: {member.filename}"
                    )
                seen_paths.add(path_key)

                if not member.is_dir():
                    if member.file_size > max_member_bytes:
                        raise ZipLimitExceededError(
                            f"A entrada excede o tamanho máximo: {member.filename}"
                        )
                    total_size += member.file_size
                    if total_size > max_uncompressed_bytes:
                        raise ZipLimitExceededError(
                            "O ZIP excede o tamanho máximo descompactado"
                        )
                validated.append((member, target))

            for member, target in validated:
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue

                target.parent.mkdir(parents=True, exist_ok=True)
                written = 0
                with archive.open(member, "r") as source, target.open("wb") as output:
                    while chunk := source.read(1024 * 1024):
                        written += len(chunk)
                        if written > max_member_bytes:
                            raise ZipLimitExceededError(
                                f"A entrada excede o tamanho máximo: {member.filename}"
                            )
                        output.write(chunk)
                extracted_files.append(str(target))

        return extracted_files
