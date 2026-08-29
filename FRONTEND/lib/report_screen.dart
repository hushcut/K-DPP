// 선택 의류의 DPP 리포트 화면을 공개하고 세부 구현을 역할별 part로 연결합니다.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'closet_provider.dart';
import 'models/clothes.dart';
import 'theme/app_palette.dart';
import 'utils/scan_form_validator.dart';

part 'report/report_body.dart';
part 'report/report_actions.dart';
part 'report/report_carbon_sections.dart';
part 'report/report_guide_sections.dart';
part 'report/report_edit_sheet.dart';

/// 현재 선택된 의류의 상세 정보와 계산 근거, 맞춤 관리·배출 안내를 표시합니다.
class ReportScreen extends StatelessWidget {
  const ReportScreen({super.key, this.onDeleted});

  final VoidCallback? onDeleted;

  @override
  Widget build(BuildContext context) {
    return _buildReportBody(context, onDeleted: onDeleted);
  }
}
