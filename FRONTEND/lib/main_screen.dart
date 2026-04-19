import 'package:flutter/material.dart';
import 'closet_screen.dart';
import 'home_screen.dart';
import 'report_screen.dart';
import 'scan_screen.dart';

class MainScreen extends StatefulWidget {
  const MainScreen({super.key});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  int _selectedIndex = 0;
  bool _didReadInitialArgs = false;

  final List<Widget> _screens = const [
    HomeScreen(),
    ScanScreen(),
    ReportScreen(),
    ClosetScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    if (!_didReadInitialArgs) {
      final args = ModalRoute.of(context)?.settings.arguments;
      if (args is int && args >= 0 && args < _screens.length) {
        _selectedIndex = args;
      }
      _didReadInitialArgs = true;
    }

    final isDark = Theme.of(context).brightness == Brightness.dark;
    final appBarIconColor = isDark ? Colors.white : const Color(0xFF1A1A1A);
    final navBackgroundColor =
    isDark ? const Color(0xFF161616) : null;

    return Scaffold(
      appBar: AppBar(
        toolbarHeight: 44,
        backgroundColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        automaticallyImplyLeading: false,
        actions: [
          IconButton(
            onPressed: () {
              Navigator.pushNamed(context, '/settings');
            },
            icon: Icon(
              Icons.settings_outlined,
              color: appBarIconColor,
            ),
          ),
        ],
      ),
      body: IndexedStack(
        index: _selectedIndex,
        children: _screens,
      ),
      bottomNavigationBar: NavigationBar(
        backgroundColor: navBackgroundColor,
        selectedIndex: _selectedIndex,
        onDestinationSelected: (index) {
          setState(() {
            _selectedIndex = index;
          });
        },
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home),
            label: '홈',
          ),
          NavigationDestination(
            icon: Icon(Icons.camera_alt_outlined),
            selectedIcon: Icon(Icons.camera_alt),
            label: '스캔',
          ),
          NavigationDestination(
            icon: Icon(Icons.article_outlined),
            selectedIcon: Icon(Icons.article),
            label: '리포트',
          ),
          NavigationDestination(
            icon: Icon(Icons.checkroom_outlined),
            selectedIcon: Icon(Icons.checkroom),
            label: '옷장',
          ),
        ],
      ),
    );
  }
}