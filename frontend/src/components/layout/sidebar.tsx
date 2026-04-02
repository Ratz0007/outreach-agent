"use client";

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { 
  LayoutDashboard, 
  Briefcase, 
  Users, 
  Send, 
  Settings, 
  ChevronRight, 
  LogOut,
  Sparkles
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';

const NAV_ITEMS = [
  { icon: LayoutDashboard, label: 'Dashboard', href: '/dashboard' },
  { icon: Briefcase, label: 'Jobs', href: '/jobs' },
  { icon: Users, label: 'Contacts', href: '/contacts' },
  { icon: Send, label: 'Outreach', href: '/outreach' },
  { icon: Settings, label: 'Settings', href: '/settings' },
];

export function Sidebar() {
  const pathname = usePathname();
  const [expanded, setExpanded] = useState(false);

  return (
    <aside 
      className={cn(
        "fixed left-0 top-0 h-screen z-40 bg-background border-r transition-all duration-300 ease-in-out",
        expanded ? "w-64 shadow-2xl" : "w-20"
      )}
      onMouseEnter={() => setExpanded(true)}
      onMouseLeave={() => setExpanded(false)}
    >
      <div className="flex flex-col h-full py-6">
        {/* Logo Area */}
        <div className="px-6 mb-10 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center text-white font-bold shrink-0">OA</div>
          {expanded && <span className="font-bold text-lg tracking-tight animate-in fade-in">Outreach Agent</span>}
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 space-y-2">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname.startsWith(item.href);
            return (
              <Link 
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-4 px-3 py-3 rounded-2xl transition-all group",
                  isActive ? "bg-primary text-primary-foreground shadow-lg shadow-primary/20" : "hover:bg-muted"
                )}
              >
                <item.icon className={cn("w-6 h-6", expanded ? "shrink-0" : "mx-auto")} />
                {expanded && <span className="font-medium animate-in fade-in slide-in-from-left-2">{item.label}</span>}
                {expanded && isActive && <ChevronRight className="w-4 h-4 ml-auto" />}
              </Link>
            );
          })}
        </nav>

        {/* Bottom Actions */}
        <div className="px-3 pt-6 border-t mt-6 space-y-2">
           <button 
             onClick={() => api.auth.logout().then(() => window.location.href = "/login")}
             className="w-full flex items-center gap-4 px-3 py-3 rounded-2xl hover:bg-destructive/10 hover:text-destructive transition-all group"
           >
              <LogOut className={cn("w-6 h-6", !expanded && "mx-auto")} />
              {expanded && <span className="font-medium">Logout</span>}
           </button>
           
           {expanded && (
             <div className="mx-3 mt-4 p-4 rounded-2xl bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-100 dark:border-indigo-800 text-xs text-indigo-700 dark:text-indigo-300">
                <div className="flex items-center gap-2 mb-2 font-bold uppercase tracking-wider tabular-nums">
                   <Sparkles className="w-3 h-3" /> Agent active
                </div>
                Your AI Career Coach is ready for voice commands.
             </div>
           )}
        </div>
      </div>
    </aside>
  );
}
