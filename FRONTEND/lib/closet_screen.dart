// 등록 의류의 검색·정렬·다중 삭제·사용자 지정 순서를 제공하는 옷장 화면입니다.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'closet_provider.dart';
import 'models/clothes.dart';

part 'closet/closet_actions.dart';
part 'closet/closet_body.dart';
part 'closet/closet_list_views.dart';
part 'closet/closet_sort_sheet.dart';

/// 옷장 목록에 적용할 정렬 기준입니다.
enum ClosetSortOption { eco, health, latest, custom }

/// 의류를 목록으로 보여 주고 선택한 항목의 상세 리포트를 여는 화면입니다.
class ClosetScreen extends StatefulWidget {
  const ClosetScreen({super.key, required this.onOpenReport, this.onStartScan});

  final ValueChanged<Clothes> onOpenReport;
  final VoidCallback? onStartScan;

  @override
  State<ClosetScreen> createState() => _ClosetScreenState();
}

/// 화면 상태만 소유하고 실제 동작과 렌더링은 역할별 part 파일에 위임합니다.
class _ClosetScreenState extends State<ClosetScreen> {
  static const double _bottomNavigationOverlapPadding = 26;

  // 다중 선택과 순서 변경은 충돌하지 않도록 서로 배타적으로 관리합니다.
  ClosetSortOption _sortOption = ClosetSortOption.eco;
  bool _selectionMode = false;
  bool _reorderMode = false;
  final Set<Clothes> _selectedItems = {};
  final TextEditingController _searchController = TextEditingController();
  String _searchQuery = '';

  @override
  void initState() {
    super.initState();
    _searchController.addListener(_handleSearchChanged);
  }

  @override
  void dispose() {
    _searchController.removeListener(_handleSearchChanged);
    _searchController.dispose();
    super.dispose();
  }

  /// part 확장이 보호 멤버인 setState를 직접 호출하지 않도록 중계합니다.
  void _updateState(VoidCallback callback) => setState(callback);

  @override
  Widget build(BuildContext context) => _buildClosetBody(context);
}
