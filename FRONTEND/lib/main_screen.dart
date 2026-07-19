// 홈·스캔·옷장 탭과 상세 리포트 전환을 한 화면에서 관리하는 앱의 메인 셸입니다.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'closet_provider.dart';
import 'closet_screen.dart';
import 'home_screen.dart';
import 'models/clothes.dart';
import 'models/main_screen_arguments.dart';
import 'report_screen.dart';
import 'scan_screen.dart';
import 'widgets/kdpp_logo_mark.dart';

/// 하단 내비게이션의 선택 상태와 리포트 오버레이 표시 상태를 관리합니다.
class MainScreen extends StatefulWidget {
  const MainScreen({super.key, this.initialArguments});

  final MainScreenArguments? initialArguments;

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  static const int _tabCount = 3;

  int _selectedIndex = 0;
  bool _didReadInitialArgs = false;
  bool _isShowingReport = false;

  // 탭을 바꾸면 열려 있던 상세 리포트도 함께 닫습니다.
  void _selectTab(int index) {
    if (index < 0 || index >= _tabCount) return;

    setState(() {
      _selectedIndex = index;
      _isShowingReport = false;
    });
  }

  // 선택 의류를 Provider에 기록한 뒤 탭 위에 상세 리포트를 표시합니다.
  void _openReport(Clothes item) {
    context.read<ClosetProvider>().selectClothes(item);

    setState(() {
      _isShowingReport = true;
    });
  }

  void _closeReport() {
    setState(() {
      _isShowingReport = false;
    });
  }

  void _handleReportDeleted() {
    setState(() {
      _selectedIndex = 2;
      _isShowingReport = false;
    });
  }

  int _normalizeInitialIndex(int index) {
    if (index == 3) return 2;

    if (index >= 0 && index < _tabCount) {
      return index;
    }

    return 0;
  }

  /// 외부 경로에서 전달된 초기 탭과 리포트 표시 요청을 한 번만 적용합니다.
  void _applyInitialArguments(Object? args) {
    if (args is MainScreenArguments) {
      _selectedIndex = _normalizeInitialIndex(args.initialIndex);
      _isShowingReport =
          args.showReport &&
          context.read<ClosetProvider>().currentReportItem != null;
      return;
    }

    _selectedIndex = _normalizeInitialIndex(args is int ? args : 0);
  }

  List<Widget> _buildTabScreens() {
    return [
      HomeScreen(
        onStartScan: () => _selectTab(1),
        onOpenReport: _openReport,
        onOpenCloset: () => _selectTab(2),
      ),
      ScanScreen(isActive: _selectedIndex == 1 && !_isShowingReport),
      ClosetScreen(onOpenReport: _openReport, onStartScan: () => _selectTab(1)),
    ];
  }

  // 탭은 IndexedStack으로 상태를 보존하고, 리포트만 AnimatedSwitcher로 교체합니다.
  Widget _buildBody() {
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 260),
      switchInCurve: Curves.easeOutCubic,
      switchOutCurve: Curves.easeInCubic,
      transitionBuilder: (child, animation) {
        final slideAnimation = Tween<Offset>(
          begin: const Offset(0.04, 0),
          end: Offset.zero,
        ).animate(animation);

        return FadeTransition(
          opacity: animation,
          child: SlideTransition(position: slideAnimation, child: child),
        );
      },
      child: _isShowingReport
          ? ReportScreen(
              key: const ValueKey('report'),
              onDeleted: _handleReportDeleted,
            )
          : IndexedStack(
              key: const ValueKey('main-tabs'),
              index: _selectedIndex,
              children: _buildTabScreens(),
            ),
    );
  }

  PreferredSizeWidget _buildAppBar(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final appBarIconColor = isDark ? Colors.white : const Color(0xFF1A1A1A);

    if (_isShowingReport) {
      return AppBar(
        toolbarHeight: 44,
        backgroundColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        leading: IconButton(
          onPressed: _closeReport,
          tooltip: '리포트 닫기',
          icon: Icon(Icons.arrow_back, color: appBarIconColor),
        ),
        title: Text(
          '상세 리포트',
          style: TextStyle(
            color: appBarIconColor,
            fontSize: 20,
            fontWeight: FontWeight.w700,
          ),
        ),
      );
    }

    return AppBar(
      toolbarHeight: 56,
      backgroundColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 0,
      automaticallyImplyLeading: false,
      centerTitle: true,
      title: const KdppLogoMark(size: 34, borderRadius: 10),
      actions: [
        IconButton(
          onPressed: () {
            Navigator.pushNamed(context, '/settings');
          },
          tooltip: '설정',
          icon: Icon(Icons.settings_outlined, color: appBarIconColor),
        ),
        const SizedBox(width: 8),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!_didReadInitialArgs) {
      final args =
          widget.initialArguments ?? ModalRoute.of(context)?.settings.arguments;
      _applyInitialArguments(args);
      _didReadInitialArgs = true;
    }

    final isDark = Theme.of(context).brightness == Brightness.dark;
    final scaffoldBg = isDark
        ? const Color(0xFF121212)
        : const Color(0xFFF8F9FC);

    return Scaffold(
      backgroundColor: scaffoldBg,
      extendBody: true,
      appBar: _buildAppBar(context),
      body: _buildBody(),
      bottomNavigationBar: _KDppBottomNavigationBar(
        selectedIndex: _selectedIndex,
        onSelect: _selectTab,
      ),
    );
  }
}

/// 좌우 탭과 가운데 돌출형 스캔 버튼을 배치하는 전용 하단 내비게이션입니다.
class _KDppBottomNavigationBar extends StatelessWidget {
  const _KDppBottomNavigationBar({
    required this.selectedIndex,
    required this.onSelect,
  });

  final int selectedIndex;
  final ValueChanged<int> onSelect;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    final pageBg = isDark ? const Color(0xFF121212) : const Color(0xFFF8F9FC);
    final barColor = isDark ? const Color(0xFF1C1C1E) : Colors.white;
    final borderColor = isDark
        ? const Color(0xFF2C2C2E)
        : const Color(0xFFE8E8EE);
    final shadowColor = isDark
        ? Colors.black.withValues(alpha: 0.30)
        : Colors.black.withValues(alpha: 0.10);

    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(18, 0, 18, 12),
        child: SizedBox(
          height: 94,
          child: Stack(
            clipBehavior: Clip.none,
            alignment: Alignment.bottomCenter,
            children: [
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                child: Container(
                  height: 70,
                  decoration: BoxDecoration(
                    color: barColor,
                    borderRadius: BorderRadius.circular(26),
                    border: Border.all(color: borderColor),
                    boxShadow: [
                      BoxShadow(
                        color: shadowColor,
                        blurRadius: 22,
                        offset: const Offset(0, 8),
                      ),
                    ],
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: _BottomTabItem(
                          icon: Icons.home_outlined,
                          activeIcon: Icons.home,
                          label: '홈',
                          selected: selectedIndex == 0,
                          onTap: () => onSelect(0),
                        ),
                      ),
                      const SizedBox(width: 88),
                      Expanded(
                        child: _BottomTabItem(
                          icon: Icons.checkroom_outlined,
                          activeIcon: Icons.checkroom,
                          label: '옷장',
                          selected: selectedIndex == 2,
                          onTap: () => onSelect(2),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              Positioned(
                top: 0,
                child: _CenterScanButton(
                  pageBg: pageBg,
                  selected: selectedIndex == 1,
                  onTap: () => onSelect(1),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// 스캔 탭을 강조하는 가운데 원형 카메라 버튼입니다.
class _CenterScanButton extends StatelessWidget {
  const _CenterScanButton({
    required this.pageBg,
    required this.selected,
    required this.onTap,
  });

  final Color pageBg;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    const activeColor = Color(0xFF4A4EFE);
    final labelColor = selected
        ? activeColor
        : (isDark ? const Color(0xFFD1D1D6) : const Color(0xFF5F6368));

    return Semantics(
      label: '스캔',
      button: true,
      selected: selected,
      child: GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: SizedBox(
          width: 88,
          height: 90,
          child: ExcludeSemantics(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 66,
                  height: 66,
                  padding: const EdgeInsets.all(5),
                  decoration: BoxDecoration(
                    color: pageBg,
                    shape: BoxShape.circle,
                  ),
                  child: Container(
                    decoration: BoxDecoration(
                      color: selected ? const Color(0xFF383CDB) : activeColor,
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                          color: activeColor.withValues(alpha: 0.34),
                          blurRadius: 18,
                          offset: const Offset(0, 8),
                        ),
                      ],
                    ),
                    child: const Icon(
                      Icons.camera_alt,
                      color: Colors.white,
                      size: 30,
                    ),
                  ),
                ),
                const SizedBox(height: 1),
                SizedBox(
                  height: 18,
                  child: Center(
                    child: Text(
                      '스캔',
                      style: TextStyle(
                        color: labelColor,
                        fontSize: 12,
                        height: 1.1,
                        fontWeight: selected
                            ? FontWeight.w700
                            : FontWeight.w500,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// 선택 상태에 따라 아이콘·색상을 바꾸는 일반 하단 탭 항목입니다.
class _BottomTabItem extends StatelessWidget {
  const _BottomTabItem({
    required this.icon,
    required this.activeIcon,
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final IconData icon;
  final IconData activeIcon;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    const activeColor = Color(0xFF4A4EFE);
    final inactiveColor = isDark
        ? const Color(0xFFD1D1D6)
        : const Color(0xFF5F6368);
    final color = selected ? activeColor : inactiveColor;

    return Semantics(
      label: label,
      button: true,
      selected: selected,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(22),
        child: SizedBox(
          height: 70,
          child: ExcludeSemantics(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(selected ? activeIcon : icon, color: color, size: 25),
                const SizedBox(height: 4),
                Text(
                  label,
                  style: TextStyle(
                    color: color,
                    fontSize: 12,
                    height: 1.1,
                    fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
