import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/store/auth";
import { useChatUnreadCount } from "@/hooks/useChatUnreadCount";

export function Nav() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const unreadCount = useChatUnreadCount();
  
  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
      <div className="max-w-3xl mx-auto px-4 h-14 flex items-center gap-4">
        <Link to="/" className="font-bold text-blue-600 text-lg">Social</Link>
        <nav className="flex gap-3 text-sm">
          <Link to="/" className="hover:underline">Feed</Link>
          <Link to="/friends" className="hover:underline">Friends</Link>
          <Link to="/chat" className="relative hover:underline">
            Chat
            {unreadCount > 0 && (
              <span className="absolute -top-2 -right-3 bg-red-500 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center">
                {unreadCount > 99 ? "99+" : unreadCount}
              </span>
            )}
          </Link>
        </nav>
        <div className="ml-auto flex items-center gap-3 text-sm">
          {user && (
            <Link to={`/profile/${user.id}`} className="hover:underline">
              {user.display_name}
            </Link>
          )}
          <button
            onClick={() => {
              logout();
              navigate("/login");
            }}
            className="text-slate-600 hover:text-red-600"
          >
            Logout
          </button>
        </div>
      </div>
    </header>
  );
}
