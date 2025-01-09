'use client';

import React, { useState, useEffect, useRef } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  Users,
  Target,
  Award,
  Lightbulb,
  Calendar,
  MapPin,
  Navigation,
} from 'lucide-react';
import Image from 'next/image';
import Link from 'next/link';
const SLIDER_IMAGES = [
  {
    url: 'https://images.unsplash.com/photo-1475721027785-f74eccf877e2?auto=format&fit=crop&q=80',
    title: 'Public Speaking Excellence',
    description:
      'Develop your communication skills through practice and feedback',
  },
  {
    url: 'https://images.unsplash.com/photo-1522071820081-009f0129c71c?auto=format&fit=crop&q=80',
    title: 'Collaborative Learning',
    description: 'Learn and grow together in a supportive environment',
  },
  {
    url: 'https://images.unsplash.com/photo-1544531585-9847b68c8c86?auto=format&fit=crop&q=80',
    title: 'Leadership Development',
    description:
      'Build confidence and leadership skills through hands-on experience',
  },
];

const ACTIVITY_GRID = [
  {
    image:
      'https://soarhigh.oss-cn-shenzhen.aliyuncs.com/public/images/meeting/weeklymeeting.jpg?x-oss-process=image/format,webp',
    title: 'Weekly Meetings',
    category: 'Learning',
  },
  {
    image:
      'https://soarhigh.oss-cn-shenzhen.aliyuncs.com/public/images/meeting/workshop.jpg?x-oss-process=image/format,webp',
    title: 'Workshop Sessions',
    category: 'Learning',
  },
  {
    image:
      'https://soarhigh.oss-cn-shenzhen.aliyuncs.com/public/images/team_building/hiking.jpg?x-oss-process=image/format,webp',
    title: 'Networking Events',
    category: 'Community',
  },
  {
    image:
      'https://soarhigh.oss-cn-shenzhen.aliyuncs.com/public/images/meeting/competition.jpg?x-oss-process=image/format,webp',
    title: 'Speech Competitions',
    category: 'Competition',
  },
  {
    image:
      'https://soarhigh.oss-cn-shenzhen.aliyuncs.com/public/images/team_building/2024ChristmasEve.jpg?x-oss-process=image/format,webp',
    title: 'Team Building',
    category: 'Community',
  },
  {
    image:
      'https://soarhigh.oss-cn-shenzhen.aliyuncs.com/public/images/meeting/leadershiptraining.jpg?x-oss-process=image/format,webp',
    title: 'Leadership Training',
    category: 'Learning',
  },
];

const LOCATION = {
  address: '宝安区宝体众里创新社区2楼',
  coordinates: {
    lat: 22.562474235254037,
    lng: 113.8739984820493,
  },
};

const MAP_LINKS = [
  {
    name: 'Google Maps',
    url: 'https://maps.app.goo.gl/t7qzRs4K3RumCw3x7',
    icon: Navigation,
  },
  {
    name: 'Baidu Maps',
    url: 'https://j.map.baidu.com/50/DFjg',
    icon: MapPin,
  },
  {
    name: 'Apple Maps',
    url: `http://maps.apple.com/?ll=${LOCATION.coordinates.lat},${LOCATION.coordinates.lng}&q=Joinin%20Hub`,
    icon: MapPin,
  },
];

const Landing = () => {
  const [currentSlide, setCurrentSlide] = useState(0);
  const [showMapMenu, setShowMapMenu] = useState(false);
  const mapMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentSlide((prev) => (prev + 1) % SLIDER_IMAGES.length);
    }, 5000);
    return () => clearInterval(timer);
  }, [currentSlide]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        mapMenuRef.current &&
        !mapMenuRef.current.contains(event.target as Node)
      ) {
        setShowMapMenu(false);
      }
    };

    if (showMapMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showMapMenu]);

  const nextSlide = () => {
    setCurrentSlide((prev) => (prev + 1) % SLIDER_IMAGES.length);
  };

  const prevSlide = () => {
    setCurrentSlide(
      (prev) => (prev - 1 + SLIDER_IMAGES.length) % SLIDER_IMAGES.length
    );
  };

  const getNextWednesday = () => {
    const today = new Date();
    const day = today.getDay(); // 0 is Sunday, 3 is Wednesday
    let daysUntilWednesday = (3 - day + 7) % 7;

    // If it's Wednesday but after 7 PM, show next Wednesday
    if (daysUntilWednesday === 0 && today.getHours() >= 19) {
      daysUntilWednesday = 7;
    }

    const nextWednesday = new Date(today);
    nextWednesday.setDate(today.getDate() + daysUntilWednesday);

    // Format: "This Wednesday" or "Next Wednesday"
    return daysUntilWednesday === 0 ? 'This Wednesday' : 'Next Wednesday';
  };

  return (
    <div className='min-h-screen bg-gray-50 w-full'>
      {/* Hero Section with Image Slider */}
      <div className='relative h-[600px] overflow-hidden'>
        {SLIDER_IMAGES.map((slide, index) => (
          <div
            key={index}
            className={`absolute inset-0 transition-opacity duration-1000 ${
              index === currentSlide ? 'opacity-100' : 'opacity-0'
            }`}
          >
            <div className='absolute inset-0 bg-black/40 z-10' />
            <Image
              src={slide.url}
              alt={slide.title}
              fill
              sizes='100vw'
              className='object-cover'
              priority={index === 0}
            />
            <div className='absolute inset-0 z-20 flex items-center justify-center text-center'>
              <div className='max-w-3xl px-4'>
                <h1 className='text-4xl sm:text-5xl md:text-6xl font-bold text-white mb-4'>
                  {slide.title}
                </h1>
                <p className='text-xl text-gray-200'>{slide.description}</p>
              </div>
            </div>
          </div>
        ))}

        <button
          onClick={prevSlide}
          className='absolute left-4 top-1/2 -translate-y-1/2 z-30 p-2 rounded-full bg-white/20 hover:bg-white/30 text-white transition-colors'
        >
          <ChevronLeft size={24} />
        </button>
        <button
          onClick={nextSlide}
          className='absolute right-4 top-1/2 -translate-y-1/2 z-30 p-2 rounded-full bg-white/20 hover:bg-white/30 text-white transition-colors'
        >
          <ChevronRight size={24} />
        </button>
      </div>

      {/* Introduction Section with CTA */}
      <div className='py-16 bg-gradient-to-b from-gray-50 to-white'>
        <div className='max-w-7xl mx-auto px-4 sm:px-6 lg:px-8'>
          <div className='max-w-3xl mx-auto text-center'>
            <h2 className='text-3xl font-bold text-gray-900 mb-6'>
              Welcome to SoarHigh
            </h2>
            <div className='prose prose-lg mx-auto text-gray-600'>
              <p className='mb-4'>
                Founded in 2020, SoarHigh is more than just a Toastmasters
                club—it&apos;s a community of passionate individuals committed
                to personal and professional growth through the art of public
                speaking.
              </p>
              <p>
                We meet weekly to practice public speaking, improve leadership
                skills, and support each other&apos;s journey to becoming
                confident communicators. Whether you&apos;re a seasoned speaker
                or just starting out, SoarHigh provides a supportive environment
                where you can develop at your own pace.
              </p>
            </div>
            <div className='mt-8 flex flex-col sm:flex-row gap-4 justify-center'>
              <div className='bg-blue-50 p-4 rounded-lg sm:w-[280px]'>
                <h3 className='font-semibold text-blue-900'>Weekly Meetings</h3>
                <p className='text-blue-700'>Every Wednesday at 7:00 PM</p>
              </div>
              <div className='bg-purple-50 p-4 rounded-lg sm:w-[280px] relative'>
                <h3 className='font-semibold text-purple-900'>Location</h3>
                <div className='flex justify-center items-center gap-1'>
                  <p className='text-purple-700'>{LOCATION.address}</p>
                  <button
                    className='p-1.5 hover:bg-purple-100 rounded-full transition-colors'
                    aria-label='Open in maps'
                    onClick={() => setShowMapMenu(!showMapMenu)}
                  >
                    <MapPin className='w-4 h-4 text-purple-700' />
                  </button>
                </div>

                {/* Map Options Menu */}
                {showMapMenu && (
                  <div
                    className='absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg py-1 z-50'
                    ref={mapMenuRef}
                  >
                    {MAP_LINKS.map((map) => (
                      <a
                        key={map.name}
                        href={map.url}
                        target='_blank'
                        rel='noopener noreferrer'
                        className='flex items-center px-4 py-2 text-sm text-gray-700 hover:bg-gray-100'
                        onClick={() => setShowMapMenu(false)}
                      >
                        <map.icon className='w-4 h-4 mr-2' />
                        {map.name}
                      </a>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Desktop CTA */}
            <div className='mt-12 hidden sm:block'>
              <Link
                href='/meetings'
                className='inline-flex items-center gap-2 px-8 py-4 text-lg font-semibold text-white bg-gradient-to-r from-blue-600 to-purple-600 rounded-full hover:from-blue-700 hover:to-purple-700 transform hover:scale-105 transition-all duration-200 shadow-lg hover:shadow-xl'
              >
                <Calendar className='w-5 h-5' />
                Join Our Next Meeting
                <span className='ml-2 text-sm bg-white/20 px-3 py-1 rounded-full'>
                  {getNextWednesday()}
                </span>
              </Link>
              <p className='mt-4 text-sm text-gray-500'>
                Experience the power of public speaking firsthand
              </p>
            </div>

            {/* Mobile Floating CTA */}
            <div className='fixed bottom-4 left-0 px-2 w-full flex justify-center sm:hidden z-50'>
              <Link
                href='/meetings'
                className='flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-semibold text-white bg-gradient-to-r from-blue-600 to-purple-600 rounded-full shadow-lg'
              >
                <Calendar className='w-4 h-4' />
                Join Our Next Meeting
                <span className='text-xs bg-white/20 px-2 py-0.5 rounded-full'>
                  {getNextWednesday()}
                </span>
              </Link>
            </div>
          </div>
        </div>
      </div>

      {/* Features Section */}
      <div className='py-16 bg-white'>
        <div className='max-w-7xl mx-auto px-4 sm:px-6 lg:px-8'>
          <div className='text-center mb-12'>
            <h2 className='text-3xl font-bold text-gray-900'>
              Why Join SoarHigh?
            </h2>
            <p className='mt-4 text-lg text-gray-600'>
              Discover the benefits of being part of our community
            </p>
          </div>

          <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8'>
            <div className='p-6 bg-gray-50 rounded-lg'>
              <Target className='w-12 h-12 text-blue-600 mb-4' />
              <h3 className='text-xl font-semibold mb-2'>Skill Development</h3>
              <p className='text-gray-600'>
                Master public speaking and leadership
              </p>
            </div>
            <div className='p-6 bg-gray-50 rounded-lg'>
              <Lightbulb className='w-12 h-12 text-blue-600 mb-4' />
              <h3 className='text-xl font-semibold mb-2'>Personal Growth</h3>
              <p className='text-gray-600'>
                Build confidence and self-improvement
              </p>
            </div>
            <div className='p-6 bg-gray-50 rounded-lg'>
              <Users className='w-12 h-12 text-blue-600 mb-4' />
              <h3 className='text-xl font-semibold mb-2'>
                Supportive Community
              </h3>
              <p className='text-gray-600'>
                Learn and grow in a welcoming environment
              </p>
            </div>
            <div className='p-6 bg-gray-50 rounded-lg'>
              <Award className='w-12 h-12 text-blue-600 mb-4' />
              <h3 className='text-xl font-semibold mb-2'>Recognition</h3>
              <p className='text-gray-600'>Earn awards and certifications</p>
            </div>
          </div>
        </div>
      </div>

      {/* Activities Grid */}
      <div className='py-16 bg-gray-50'>
        <div className='max-w-7xl mx-auto px-4 sm:px-6 lg:px-8'>
          <div className='text-center mb-12'>
            <h2 className='text-3xl font-bold text-gray-900'>
              Club Activities
            </h2>
            <p className='mt-4 text-lg text-gray-600'>
              Explore our diverse range of activities and events
            </p>
          </div>

          <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8'>
            {ACTIVITY_GRID.map((activity, index) => (
              <div
                key={index}
                className='group relative overflow-hidden rounded-lg shadow-lg aspect-[4/3]'
              >
                <Image
                  src={activity.image}
                  alt={activity.title}
                  fill
                  sizes='(max-width: 768px) 100vw, (max-width: 1200px) 50vw, 33vw'
                  className='object-cover transition-transform duration-500 group-hover:scale-110'
                  loading='lazy'
                />
                <div className='absolute inset-0 bg-gradient-to-t from-black/70 to-transparent flex items-end p-6'>
                  <div>
                    <span className='text-sm font-medium text-blue-400'>
                      {activity.category}
                    </span>
                    <h3 className='text-xl font-bold text-white mt-2'>
                      {activity.title}
                    </h3>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Landing;
