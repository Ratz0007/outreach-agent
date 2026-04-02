"use client";

import React, { useState, useEffect } from 'react';
import { 
  Bell, 
  Search, 
  User, 
  Moon, 
  Sun,
  Settings,
  HelpCircle,
  LogOut,
  ChevronDown
} from 'lucide-react';
import { useTheme } from 'next-themes';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';

export function TopBar() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [user, setUser] = useState<any>(null);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  // Avoid hydration mismatch
  useEffect(() => {
    setMounted(true);
    api.auth.me().then(setUser).catch(() => {});
  }, []);

  if (!mounted) return null;

  return (
    <header className="h-20 border-b bg-background/80 backdrop-blur-md sticky top-0 z-30 px-6 flex items-center justify-between">
      <div className="flex-1 flex items-center gap-4">
        <div className="relative max-w-md w-full group">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground group-focus-within:text-primary transition-colors" />
          <input 
            type="text" 
            placeholder="Search for jobs, contacts, or messages..." 
            className="w-full h-11 bg-muted/50 border-none rounded-2xl pl-12 pr-4 text-sm focus:ring-2 focus:ring-primary/20 focus:bg-background transition-all outline-none"
          />
        </div>
      </div>

      <div className="flex items-center gap-2">
        {/* Theme Toggle */}
        <Button 
          variant="outline" 
          size="icon" 
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          className="rounded-2xl border-none bg-muted/50 w-11 h-11"
        >
          {theme === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
        </Button>

        {/* Notifications */}
        <Button 
          variant="outline" 
          size="icon" 
          className="rounded-2xl border-none bg-muted/50 w-11 h-11 relative"
        >
          <Bell className="w-5 h-5" />
          <span className="absolute top-2.5 right-2.5 w-2 h-2 rounded-full bg-destructive border-2 border-background" />
        </Button>

        <div className="w-[1px] h-6 bg-border mx-2" />

        {/* User Profile Dropdown */}
        <div className="relative">
          <button 
            onClick={() => setIsDropdownOpen(!isDropdownOpen)}
            className="flex items-center gap-3 pl-2 pr-1 py-1 rounded-2xl hover:bg-muted transition-all"
          >
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-500 to-purple-600 flex items-center justify-center text-white text-xs font-bold shadow-lg shadow-indigo-500/20">
              {user?.full_name?.split(' ').map((n: string) => n[0]).join('') || 'U'}
            </div>
            <div className="hidden md:block text-left">
               <p className="text-sm font-bold truncate leading-none mb-1">{user?.full_name || user?.username}</p>
               <p className="text-[10px] text-muted-foreground uppercase tracking-widest font-black leading-none">{user?.email ? 'Pro Plan' : 'Free Plan'}</p>
            </div>
            <ChevronDown className={cn("w-4 h-4 text-muted-foreground transition-transform", isDropdownOpen && "rotate-180")} />
          </button>

          {isDropdownOpen && (
            <div className="absolute right-0 mt-3 w-56 bg-background rounded-3xl border shadow-2xl p-2 animate-in fade-in slide-in-from-top-2">
               <div className="px-4 py-3 border-b mb-1">
                  <p className="text-xs text-muted-foreground mb-1">Signed in as</p>
                  <p className="text-sm font-bold truncate">{user?.email || user?.username}</p>
               </div>
               <div className="space-y-1">
                 <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-2xl hover:bg-muted text-sm font-medium transition-all">
                    <User className="w-4 h-4" /> Profile Details
                 </button>
                 <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-2xl hover:bg-muted text-sm font-medium transition-all">
                    <Settings className="w-4 h-4" /> Workspace Settings
                 </button>
                 <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-2xl hover:bg-muted text-sm font-medium transition-all">
                    <HelpCircle className="w-4 h-4" /> Troubleshooting
                 </button>
                 <div className="mt-2 pt-2 border-t">
                    <button 
                      onClick={() => api.auth.logout().then(() => window.location.href = "/login")}
                      className="w-full flex items-center gap-3 px-3 py-2.5 rounded-2xl hover:bg-destructive/10 hover:text-destructive text-sm font-bold transition-all"
                    >
                       <LogOut className="w-4 h-4" /> Logout
                    </button>
                 </div>
               </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
