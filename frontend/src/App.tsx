import { useEffect } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import { auth as authApi } from "@/api/endpoints";
import { Nav } from "@/components/Nav";
import { useAuth } from "@/store/auth";

import FeedPage from "@/pages/FeedPage";
import LoginPage from "@/pages/LoginPage";
import RegisterPage from "@/pages/RegisterPage";
import ProfilePage from "@/pages/ProfilePage";
import FriendsPage from "@/pages/FriendsPage";
import ChatPage from "@/pages/ChatPage";

function Protected({ children }: { children: JSX.Element }) {
  const token = useAuth((s) => s.token);
  const location = useLocation();
  if (!token) return <Navigate to="/login" replace state={{ from: location }} />;
  return children;
}

export default function App() {
  const { token, user, setUser, logout } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (token && !user) {
      authApi.me().then(setUser).catch(() => {
        logout();
        navigate("/login");
      });
    }
  }, [token, user, setUser, logout, navigate]);

  return (
    <div className="min-h-screen">
      {token && <Nav />}
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/" element={<Protected><FeedPage /></Protected>} />
        <Route path="/profile/:userId" element={<Protected><ProfilePage /></Protected>} />
        <Route path="/friends" element={<Protected><FriendsPage /></Protected>} />
        <Route path="/chat" element={<Protected><ChatPage /></Protected>} />
        <Route path="/chat/:roomId" element={<Protected><ChatPage /></Protected>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}
