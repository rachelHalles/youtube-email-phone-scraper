import csv
import html
import json
from pathlib import Path
from typing import Dict, Iterable, List, Mapping

from parsers.youtube_parser import ChannelContact  # type: ignore

class ExportManager:
    """
    Handles multi-format export of scraped contact data.
    Supported formats: json, csv, xml, html
    """

    def __init__(self, output_dir: Path, logger) -> None:
        self.output_dir = output_dir
        self.logger = logger
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export(
        self,
        contacts: Iterable[ChannelContact],
        formats: Iterable[str],
    ) -> Dict[str, Path]:
        contacts_list: List[ChannelContact] = list(contacts)
        results: Dict[str, Path] = {}

        normalized_formats = {fmt.lower().strip() for fmt in formats}
        if not normalized_formats:
            normalized_formats = {"json"}

        for fmt in normalized_formats:
            if fmt == "json":
                results["json"] = self._export_json(contacts_list)
            elif fmt == "csv":
                results["csv"] = self._export_csv(contacts_list)
            elif fmt == "xml":
                results["xml"] = self._export_xml(contacts_list)
            elif fmt == "html":
                results["html"] = self._export_html(contacts_list)
            else:
                self.logger.warning("Unknown export format '%s'; skipping.", fmt)

        return results

    def _contacts_to_dicts(self, contacts: List[ChannelContact]) -> List[Mapping]:
        return [c.to_dict() for c in contacts]

    def _export_json(self, contacts: List[ChannelContact]) -> Path:
        path = self.output_dir / "contacts.json"
        self.logger.debug("Exporting JSON to %s", path)
        data = self._contacts_to_dicts(contacts)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path

    def _export_csv(self, contacts: List[ChannelContact]) -> Path:
        path = self.output_dir / "contacts.csv"
        self.logger.debug("Exporting CSV to %s", path)
        rows = self._contacts_to_dicts(contacts)
        if not rows:
            # Still create an empty file with headers
            headers = [
                "Channel_url",
                "Channel_name",
                "Email",
                "Domain_email",
                "Phone",
                "Description",
            ]
        else:
            headers = list(rows[0].keys())
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        return path

    def _export_xml(self, contacts: List[ChannelContact]) -> Path:
        path = self.output_dir / "contacts.xml"
        self.logger.debug("Exporting XML to %s", path)
        rows = self._contacts_to_dicts(contacts)

        def esc(value: str) -> str:
            return html.escape(value or "", quote=True)

        xml_parts: List[str] = ['<?xml version="1.0" encoding="UTF-8"?>', "<contacts>"]
        for row in rows:
            xml_parts.append("  <contact>")
            for key, value in row.items():
                xml_parts.append(
                    f"    <{key}>{esc(str(value))}</{key}>"
                )
            xml_parts.append("  </contact>")
        xml_parts.append("</contacts>")

        with path.open("w", encoding="utf-8") as f:
            f.write("\n".join(xml_parts))

        return path

    def _export_html(self, contacts: List[ChannelContact]) -> Path:
        path = self.output_dir / "contacts.html"
        self.logger.debug("Exporting HTML to %s", path)
        rows = self._contacts_to_dicts(contacts)

        headers = [
            "Channel_url",
            "Channel_name",
            "Email",
            "Domain_email",
            "Phone",
            "Description",
        ]

        def esc(value: str) -> str:
            return html.escape(value or "", quote=True)

        lines: List[str] = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            '  <meta charset="utf-8" />',
            "  <title>YouTube Contacts Export</title>",
            "  <style>",
            "    table { border-collapse: collapse; width: 100%; }",
            "    th, td { border: 1px solid #ddd; padding: 8px; font-family: Arial, sans-serif; font-size: 14px; }",
            "    th { background-color: #f4f4f4; text-align: left; }",
            "    tr:nth-child(even) { background-color: #fbfbfb; }",
            "  </style>",
            "</head>",
            "<body>",
            "  <h1>YouTube Contacts Export</h1>",
            "  <table>",
            "    <thead>",
            "      <tr>",
        ]
        for h in headers:
            lines.append(f"        <th>{esc(h)}</th>")
        lines.extend(
            [
                "      </tr>",
                "    </thead>",
                "    <tbody>",
            ]
        )

        for row in rows:
            lines.append("      <tr>")
            for h in headers:
                value = str(row.get(h, ""))
                if h == "Channel_url" and value:
                    cell = f'<a href="{esc(value)}" target="_blank">{esc(value)}</a>'
                else:
                    cell = esc(value)
                lines.append(f"        <td>{cell}</td>")
            lines.append("      </tr>")

        lines.extend(
            [
                "    </tbody>",
                "  </table>",
                "</body>",
                "</html>",
            ]
        )

        with path.open("w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return path