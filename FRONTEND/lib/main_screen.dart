import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'closet_provider.dart';
import 'closet_screen.dart';
import 'home_screen.dart';
import 'models/clothes.dart';
import 'report_screen.dart';
import 'scan_screen.dart';

class MainScreen extends StatefulWidget {
  const MainScreen({super.key});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  static const int _tabCount = 3;

  int _selectedIndex = 0;
  bool _didReadInitialArgs = false;
  bool _isShowingReport = false;

  void _selectTab(int index) {
    if (index < 0 || index >= _tabCount) return;

    setState(() {
      _selectedIndex = index;
      _isShowingReport = false;
    });
  }

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

  int _normalizeInitialIndex(Object? args) {
    if (args is! int) return 0;
    if (args == 3) return 2;

    if (args >= 0 && args < _tabCount) {
      return args;
    }

    return 0;
  }

  List<Widget> _buildTabScreens() {
    return [
      const HomeScreen(),
      ScanScreen(isActive: _selectedIndex == 1 && !_isShowingReport),
      ClosetScreen(onOpenReport: _openReport),
    ];
  }

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
          ? const ReportScreen(key: ValueKey('report'))
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
      title: const _KDppSplashLogoMark(),
      actions: [
        IconButton(
          onPressed: () {
            Navigator.pushNamed(context, '/settings');
          },
          icon: Icon(Icons.settings_outlined, color: appBarIconColor),
        ),
        const SizedBox(width: 8),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!_didReadInitialArgs) {
      final args = ModalRoute.of(context)?.settings.arguments;
      _selectedIndex = _normalizeInitialIndex(args);
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

class _KDppSplashLogoMark extends StatelessWidget {
  const _KDppSplashLogoMark();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 34,
      height: 34,
      decoration: BoxDecoration(
        color: const Color(0xFF4A4EFE),
        borderRadius: BorderRadius.circular(10),
      ),
      child: const Icon(Icons.eco_outlined, color: Colors.white, size: 21),
    );
  }
}

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
        : (isDark ? const Color(0xFFD1D1D6) : Colors.grey);

    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: SizedBox(
        width: 88,
        height: 90,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 66,
              height: 66,
              padding: const EdgeInsets.all(5),
              decoration: BoxDecoration(color: pageBg, shape: BoxShape.circle),
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
                    fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

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
    final inactiveColor = isDark ? const Color(0xFFD1D1D6) : Colors.grey;
    final color = selected ? activeColor : inactiveColor;

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(22),
      child: SizedBox(
        height: 70,
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
    );
  }
}
