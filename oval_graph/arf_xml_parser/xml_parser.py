"""
    This file contains a class for creating OVAL graph from ARF XML source
"""

import os
import sys

from lxml import etree as ET

from ._xml_parser_oval_scan_definitions import _XmlParserScanDefinitions
from ..exceptions import NotTestedRule
from ..oval_tree.builder import Builder

ns = {
    'XMLSchema': 'http://oval.mitre.org/XMLSchema/oval-results-5',
    'xccdf': 'http://checklists.nist.gov/xccdf/1.2',
    'arf': 'http://scap.nist.gov/schema/asset-reporting-format/1.1',
    'oval-definitions': 'http://oval.mitre.org/XMLSchema/oval-definitions-5',
    'scap': 'http://scap.nist.gov/schema/scap/source/1.2',
    'oval-characteristics': 'http://oval.mitre.org/XMLSchema/oval-system-characteristics-5',
}


class XmlParser:
    def __init__(self, src):
        self.src = src
        self.tree = ET.parse(self.src)
        self.root = self.tree.getroot()
        self.arf_schemas_src = '../schemas/arf/1.1/asset-reporting-format_1.1.0.xsd'
        if not self.validate(self.arf_schemas_src):
            start_red_color = '\033[91m'
            end_red_color = '\033[0m'
            message = "{}Warning: This file is not valid arf report.{}".format(
                start_red_color, end_red_color)
            print(message, file=sys.stderr)
        try:
            self.used_rules, self.not_tested_rules = self._get_rules_in_profile()
            self.report_data_href = list(self.used_rules.values())[0]['href']
            self.report_data = self._get_report_data(self.report_data_href)
            self.definitions = self._get_definitions()
            self.oval_definitions = self._get_oval_definitions()
            self.scan_definitions = _XmlParserScanDefinitions(
                self.definitions, self.oval_definitions, self.report_data).get_scan()
        except BaseException:
            raise ValueError(
                'This file "{}" is not arf report file or there are no results'.format(
                    self.src))

    @staticmethod
    def get_src(src):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        return str(os.path.join(dir_path, src))

    def validate(self, xsd_path):
        xsd_path = self.get_src(xsd_path)
        xmlschema_doc = ET.parse(xsd_path)
        xmlschema = ET.XMLSchema(xmlschema_doc)
        return xmlschema.validate(self.tree)

    @staticmethod
    def _get_rule_dict(rule_result, result, id_def, check_content_ref):
        message = rule_result.find('.//xccdf:message', ns)
        rule_dict = {}
        rule_dict['id_def'] = id_def
        rule_dict['href'] = check_content_ref.attrib.get('href')
        rule_dict['result'] = result.text
        if message is not None:
            rule_dict['message'] = message.text
        return rule_dict

    def _get_rules_in_profile(self):
        rules_results = self.root.findall(
            './/xccdf:TestResult/xccdf:rule-result', ns)
        rules = {}
        not_tested_rules = {}
        for rule_result in rules_results:
            result = rule_result.find('.//xccdf:result', ns)
            check_content_ref = rule_result.find(
                './/xccdf:check/xccdf:check-content-ref', ns)
            if check_content_ref is not None:
                id_ = rule_result.get('idref')
                id_def = check_content_ref.attrib.get('name')
                if id_def is not None:
                    rules[id_] = self._get_rule_dict(
                        rule_result, result, id_def, check_content_ref)
                    continue
            not_tested_rules[rule_result.get('idref')] = result.text
        return (rules, not_tested_rules)

    def _get_report_data(self, href):
        report_data = None
        reports = self.root.find('.//arf:reports', ns)
        for report in reports:
            if "#" + str(report.get("id")) == href:
                report_data = report
        return report_data

    def _get_definitions(self):
        return self.report_data.find(
            ('.//XMLSchema:oval_results/XMLSchema:results/'
             'XMLSchema:system/XMLSchema:definitions'), ns)

    def _get_oval_definitions(self):
        return self.root.find(
            './/arf:report-requests/arf:report-request/'
            'arf:content/scap:data-stream-collection/'
            'scap:component/oval-definitions:oval_definitions/'
            'oval-definitions:definitions', ns)

    def _get_definition_of_rule(self, rule_id):
        if rule_id in self.used_rules:
            rule_info = self.used_rules[rule_id]
            return dict(rule_id=rule_id,
                        definition_id=rule_info['id_def'],
                        definition=self.scan_definitions[rule_info['id_def']])

        if rule_id in self.not_tested_rules:
            raise NotTestedRule(
                'Rule "{}" is {}, so there are no results.'
                .format(rule_id, self.not_tested_rules[rule_id]))
        raise ValueError('404 rule "{}" not found!'.format(rule_id))

    def get_oval_tree(self, rule_id):
        return Builder.dict_of_rule_to_oval_tree(
            self._get_definition_of_rule(rule_id))
