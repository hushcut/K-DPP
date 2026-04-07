import 'package:flutter/material.dart';
import 'home_screen.dart';
import 'scan_screen.dart';
import 'report_screen.dart';
import 'closet_screen.dart';

class MainScreen extends StatefulWidget {
  const MainScreen({super.key});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  int _selectedIndex = 0;
  bool _didLoadInitialRouteArgument = false;

  final List<Widget> _screens = const [
    HomeScreen(),
    ScanScreen(),
    ReportScreen(),
    ClosetScreen(),
  ];

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();

    if (_didLoadInitialRouteArgument) return;

    final route = ModalRoute.of(context);
    final args = route?.settings.arguments;

    if (args is int && args >= 0 && args < _screens.length) {
      _selectedIndex = args;
    }

    _didLoadInitialRouteArgument = true;
  }

  void _onItemTapped(int index) {
    setState(() {
      _selectedIndex = index;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('K-DPP', style: TextStyle(fontWeight: FontWeight.bold)),
        backgroundColor: Colors.white,
        foregroundColor: Colors.black,
        elevation: 0,
        centerTitle: true,
      ),
      body: IndexedStack(
        index: _selectedIndex,
        children: _screens,
      ),
      bottomNavigationBar: BottomNavigationBar(
        type: BottomNavigationBarType.fixed,
        backgroundColor: Colors.white,
        selectedItemColor: const Color(0xFF4A4EFE),
        unselectedItemColor: Colors.grey,
        currentIndex: _selectedIndex,
        onTap: _onItemTapped,
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.home_outlined),
            activeIcon: Icon(Icons.home),
            label: '홈',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.camera_alt_outlined),
            activeIcon: Icon(Icons.camera_alt),
            label: '스캔',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.analytics_outlined),
            activeIcon: Icon(Icons.analytics),
            label: '리포트',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.checkroom_outlined),
            activeIcon: Icon(Icons.checkroom),
            label: '옷장',
          ),
        ],
      ),
    );
  }
}