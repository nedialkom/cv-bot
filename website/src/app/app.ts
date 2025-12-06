import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';

interface Experience {
  company: string;
  role: string;
  period: string;
  location: string;
  bullets: string[];
}

interface Highlight {
  title: string;
  description: string;
  year?: string;
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.html',
  styleUrls: ['./app.scss'],
})
export class App implements OnInit {
  constructor(private http: HttpClient, private cdr: ChangeDetectorRef) {}

  sections = [
    { id: 'about', label: 'About' },
    { id: 'highlights', label: 'Highlights' },
    { id: 'experience', label: 'Experience' },
  ];

  name = '';
  title = '';
  location = '';
  companyTagline = '';
  aboutShort = '';
  aboutLong = '';
  experience: Experience[] = [];
  highlights: Highlight[] = [];
  phone = '';
  email = '';
  linkedInUrl = '';
  bankSite = '';

  // Chatbot properties
  chatOpen = true;
  currentMessage = '';
  messages: { text: string; isUser: boolean }[] = [];
  isLoading = false;

  ngOnInit() {
    this.loadConfig();
    // Add initial message immediately
    this.messages.push({
      text: "Hello! I'm Nedyalko Mihaylov. I'm here to answer questions about my professional experience and background. What would you like to know?",
      isUser: false
    });
  }

  loadConfig() {
    this.http.get('/settings/config.txt', { responseType: 'text' }).subscribe({
      next: (data) => {
        const config = JSON.parse(data);
        this.name = config.name || 'Name not found';
        this.title = config.title || 'Title not found';
        this.location = config.location || 'Location not found';
        this.companyTagline = config.companyTagline || '';
        this.aboutShort = config.aboutShort || 'About short not found';
        this.aboutLong = config.aboutLong || 'About long not found';
        this.experience = config.experience || [];
        this.highlights = config.highlights || [];
        this.phone = config.phone || '';
        this.email = config.email || '';
        this.linkedInUrl = config.linkedInUrl || '';
        this.bankSite = config.bankSite || '';

        // Load chatbot config
        if (config.chatbot && config.chatbot.initialState) {
          this.chatOpen = config.chatbot.initialState === 'open';
        }
        this.cdr.detectChanges();
      },
      error: (error) => {
        console.error('Error loading config:', error);
        // Set fallback values
        this.name = 'Config Load Error';
        this.title = 'Please check console';
        this.aboutShort = 'Failed to load configuration';
      }
    });
  }

  scrollTo(sectionId: string) {
    const el = document.getElementById(sectionId);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  toggleChat() {
    this.chatOpen = !this.chatOpen;
  }

  async sendMessage() {
    if (!this.currentMessage.trim()) return;

    // Add user message
    this.messages.push({ text: this.currentMessage, isUser: true });
    this.scrollToBottom();

    // Call bot API
    await this.getBotResponse(this.currentMessage);
    this.currentMessage = '';
  }

  private scrollToBottom(): void {
    setTimeout(() => {
      const messagesContainer = document.querySelector('.messages');
      if (messagesContainer) {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
      }
    }, 100);
  }

  private async getBotResponse(message: string): Promise<void> {
    const botUrl = '/api/chat';
    this.isLoading = true;

    try {
      const data = await this.http.post<{response: string}>(botUrl, { message }).toPromise();
      this.isLoading = false;
      this.messages.push({ text: data!.response, isUser: false });
      this.cdr.detectChanges();
      this.scrollToBottom();
    } catch (error) {
      this.isLoading = false;
      console.error('Bot API error:', error);
      this.messages.push({
        text: 'I\'m having trouble connecting right now. Please try again later.',
        isUser: false
      });
      this.cdr.detectChanges();
      this.scrollToBottom();
    }
  }
}
