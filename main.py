import argparse
import datetime
import json
import os
import sys
from typing import Dict, List, Tuple, Optional
from WazeRouteCalculator import WazeRouteCalculator

class RouteCache:
    #adding cache to save wazeapi calls
    def __init__(self, cache_file="route_cache.json"):
        self.cache_file = cache_file
        self.cache = self.load_cache()
        
    def load_cache(self) -> Dict:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"problem with cache - error {e}")
        return {"routes": {}}
    
    def save_cache(self):
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            print(f"problem with cache - error {e}")
    
    def get_cache_key(self, source: str, destination: str) -> str:
        return f"{source.lower()}|{destination.lower()}"
        
    
    def get_route(self, source: str, destination: str) -> Tuple[float, float]:
        cache_key = self.get_cache_key(source, destination)
        if cache_key in self.cache["routes"]:
            print(f"get data from cache - {source} to {destination}")
            return tuple(self.cache["routes"][cache_key])
        return
    
    def store_route(self, source: str, destination: str, route_data: Tuple[float, float]):
        cache_key = self.get_cache_key(source, destination)
        self.cache["routes"][cache_key] = route_data
        self.save_cache()


class Segment:    
    def __init__(self, source: str, destination: str, duration_minutes: float, 
                    distance_km: float, stop_duration_minutes: int = 0):
        self.source = source
        self.destination = destination
        self.duration_minutes = duration_minutes
        self.distance_km = distance_km
        self.stop_duration_minutes = stop_duration_minutes
    
    def get_total_duration(self) -> float:
        return self.duration_minutes + self.stop_duration_minutes
    
    def __str__(self) -> str:
        return (f"from {self.source} to {self.destination}: "
                f"{self.duration_minutes:.1f} minutes ({self.distance_km:.1f} km), "
                f"stopping for {self.stop_duration_minutes} minutes")


class Route:    
    #every route is array of 
    def __init__(self, source: str, destination: str, arrival_time: datetime.time):
        self.source = source
        self.destination = destination
        self.arrival_time = arrival_time
        self.segments: List[Segment] = []
    
    def add_segment(self, segment: Segment):
        self.segments.append(segment)
    
    def get_total_duration(self) -> float:
        total = 0.0
        for segment in self.segments:
            total += segment.duration_minutes 
        return total
    
    def calculate_departure_times(self) -> Dict[str, datetime.time]:
        #main logic - start from arrival time and work backwards
        #add stops to total time
        if not self.segments:
            return {}
        
        departure_times = {}
        current_time = datetime.datetime.combine(datetime.date.today(), self.arrival_time)
        
        for segment in reversed(self.segments):
            # Set arrival time as destination
            # Subtract segment duration to get departure time from source, segment after segment
            current_time = current_time - datetime.timedelta(minutes=segment.duration_minutes)
            departure_times[segment.source] = current_time.time()
            
            # Subtract stop duration for next calculation check if > 0
            if segment.stop_duration_minutes > 0:
                current_time = current_time - datetime.timedelta(minutes=segment.stop_duration_minutes)
        
        return departure_times


class WazeAPI:    
    def __init__(self, region='IL'):
        self.region = region
    
    def get_route(self, source: str, destination: str) -> Tuple[float, float]:
        try:
            calculator = WazeRouteCalculator(source, destination, self.region)
            return calculator.calc_route_info()
        except Exception as e:
            print(f"error calculating route: {e}")
            return (0, 0)


class WazeRouteCacheCalculator:
    def __init__(self, cache_file, region):
        self.cache = RouteCache(cache_file)
        self.api = WazeAPI(region)
    
    def calculate_route_segment(self, source: str, destination: str) -> Tuple[float, float]:
        #cache first policy 
        route_data = self.cache.get_route(source, destination)
        
        if route_data is None:
            route_data = self.api.get_route(source, destination)
            self.cache.store_route(source, destination, route_data)
        
        return route_data
    
    def build_route(self, source: str, destination: str, 
                   stops: List[Tuple[str, int]], arrival_time: datetime.time) -> Route:
        route = Route(source, destination, arrival_time)     
        # Start with source
        current_location = source
        for next_location, stop_duration in stops:
            duration, distance = self.calculate_route_segment(current_location, next_location)
            #iterate over stops and add segment
            segment = Segment(
                source=current_location,
                destination=next_location,
                duration_minutes=duration,
                distance_km=distance,
                stop_duration_minutes=stop_duration
            )
            route.add_segment(segment)
            current_location = next_location
        
        # Add final segment to destination
        duration, distance = self.calculate_route_segment(current_location, destination)
        final_segment = Segment(
            source=current_location,
            destination=destination,
            duration_minutes=duration,
            distance_km=distance,
            stop_duration_minutes=0
        )
        route.add_segment(final_segment)
        
        return route
    
    def get_departure_time(self, source: str, destination: str, 
                         stops: List[Tuple[str, int]], arrival_time: datetime.time) -> datetime.time:
        route = self.build_route(source, destination, stops, arrival_time)
        departure_times = route.calculate_departure_times()
        return departure_times[source]


class InputParser:
    def parse_stops(stops_str: str) -> List[Tuple[str, int]]:
        if not stops_str:
            return []
        
        parts = stops_str.split(',')
        if len(parts) % 2 != 0:
            raise ValueError("stops must be in pairs of location,duration")
        
        stops = []
        for i in range(0, len(parts), 2):
            location = parts[i]
            duration_str = parts[i+1]
            
            # Parse duration like "1h" or "15m"
            if duration_str.endswith('h'):
                duration = int(duration_str[:-1]) * 60
            elif duration_str.endswith('m'):
                duration = int(duration_str[:-1])
            else:
                try:
                    duration = int(duration_str)
                except ValueError:
                    raise ValueError(f"invalid duration format: {duration_str}")
            
            stops.append((location, duration))
        
        return stops
    
    def parse_time(time_str: str) -> datetime.time:
        try:
            return datetime.datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            raise ValueError(f"Invalid time format: {time_str}. Expected HH:MM")


def main():
    #read the args and orchestrate route
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", required=True)
    parser.add_argument("--dst", required=True)
    parser.add_argument("--stops")
    parser.add_argument("--arrival_time", required=True)
    
    args = parser.parse_args()
    
    stops = InputParser.parse_stops(args.stops) if args.stops else []
    arrival_time = InputParser.parse_time(args.arrival_time)
    
    calculator = WazeRouteCacheCalculator(cache_file="route_cache.json", region='IL')
    departure_time = calculator.get_departure_time(args.src, args.dst, stops, arrival_time)
    
    #print result
    print(f"output: leave {args.src} at {departure_time.strftime('%H:%M')} to reach {args.dst} by {args.arrival_time}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())