import 'package:shared_preferences/shared_preferences.dart';

class AuthSessionService {
  const AuthSessionService();

  static const _accessTokenKey = 'auth_access_token';

  Future<void> saveAccessToken(String token) async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(_accessTokenKey, token);
  }

  Future<String?> readAccessToken() async {
    final preferences = await SharedPreferences.getInstance();
    return preferences.getString(_accessTokenKey);
  }

  Future<void> clear() async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.remove(_accessTokenKey);
  }
}
