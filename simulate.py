# python 3

import json
import numpy as np
import random



class Manager():
    
    def __init__(self, path_to_player_file,path_to_price_file,path_to_sun_file,path_to_industrial_demand_file,path_to_planning_file): #constructor
        
        self.horizon = 48
        self.dt = 0.5
        
        self.nb_tot_players = 0
        self.nb_players = {"charging_station":0,"industrial_consumer":0,"solar_farm":0}

        self.players = self.initialize_players(path_to_player_file)
        
        self.prices = self.initialize_prices(path_to_price_file)
        self.data_scenario=self.initialize_data_scenario(path_to_sun_file,path_to_industrial_demand_file,path_to_planning_file)
        
        self.imbalance=np.zeros((2,self.horizon))
        self.grid_load={"demand": np.zeros(self.horizon), "supply": np.zeros(self.horizon) }
        self.scenario={"planning":np.zeros((2,4)),"sunshine":np.zeros(self.horizon),"industrial demand":np.zeros(self.horizon)}
        
        

    def initialize_players(self, json_file):

        with open(json_file) as f:
            players = json.load(f)
            

        new_players = {}

        for idx in players:
            
            self.nb_players[players[idx]["type"]] +=1
            
            self.nb_tot_players+=1
            mod = __import__("players.{}.player".format(players[idx]["folder"]), 
                fromlist=["Player"])
            Player = getattr(mod, "Player")
            new_player = Player() # if you want to initialize with parameters, you have to distinguish types of players... do we want that ?
            
            new_players[idx] = {"class":new_player, "type":players[idx]["type"]}
            

        return new_players
        
## Initialize the prices for the day

    def initialize_prices(self, path_to_price_file):
        
        prices=np.loadtxt("data/prices.csv") #internal prices, external purchase prices, external sale prices
        dico_prices={"internal" : prices[0, :], "external_purchase" : prices[1, :], "external_sale" : prices[2, :]}
        return dico_prices


## Initialize all the scenarios possible

    def initialize_data_scenario(self,path_to_sun_file,path_to_industrial_demand_file,path_to_planning_file):
        
        pv_scenarios=np.loadtxt(path_to_sun_file) #photovoltaic production per slot, 100 scenarios
        ldem_scenarios=np.loadtxt(path_to_industrial_demand_file)  #industrial needs per slot, 100 scenarios
        planning_scenarios=np.genfromtxt(path_to_planning_file,delimiter= ";") #departure and arrival time of each car, 100 scenarios
        dico_data_scenario={"planning":planning_scenarios,"sunshine":pv_scenarios,"industrial demand":ldem_scenarios}
        
        return dico_data_scenario
        
## Draw a scenario for the day
    
    def draw_random_scenario(self):
        

        pv=self.data_scenario["sunshine"][random.randint(0,len(self.data_scenario["sunshine"])-1)] #sunshine data
        ldem=self.data_scenario["industrial demand"][random.randint(0,len(self.data_scenario["industrial demand"])-1)] #industrial consumer need 
        p=random.randint(0,len(self.data_scenario["planning"])/2 -1) 
        planning=np.array([self.data_scenario["planning"][:,2*p], self.data_scenario["planning"][:,2*p+1]]) #departure and arrival of each car
        scenario={"planning":planning,"sunshine":pv,"industrial demand":ldem}
        
        self.scenario=scenario
        
        return pv,ldem,planning
        
           ##Compute the energy balance on a slot
    def energy_balance(self, time):

        demand = 0
        supply = 0

        for idx,dico in self.players.items():
            
            player = dico["class"]
            data_scenario = { "sun" : self.scenario["sunshine"][time],"demand" : self.scenario["industrial demand"][time]}
            player.compute_load(time,data_scenario)
            load = player.load[time]

            if load >= 0: #if the player needs energy
                demand += load
            else:         #if the player supply energy
                supply -= load
        
        self.grid_load["demand"][time]=demand
        self.grid_load["supply"][time]=supply
        
        return  demand, supply


    ## Compute the bill of each players 
    def compute_bills(self, time, demand, supply):
        total_load=demand-supply    #total load of the grid
        internal_exchange=min(demand,supply)  #what is going to be exchange on the grid
        external_exchange=abs(total_load)   #the quantity of energy in surplus on the grid
        internal_price=self.prices["internal"][time]
        external_selling_price=self.prices["external_sale"][time]
        external_purchasing_price=self.prices["external_purchase"][time]

        if total_load>=0:  #if there is not enough energy on the grid
            
            proportion_internal_demand=internal_exchange/demand
            proportion_internal_supply=1
            
            self.imbalance[0][time] = proportion_internal_demand
            self.imbalance[1][time] = proportion_internal_supply

            for idx,dico in self.players.items():
                
                player = dico["class"]

                load=player.load[time]

                if load>0: #if the player needs energy

                    cost= (internal_price*(proportion_internal_demand) + external_purchasing_price*(1-proportion_internal_demand))*load*self.dt
                            #the players pays in proportion on and off the grid for his demand
                    player.bill[time] += cost

                elif load<0: #if the player supply energy

                    revenue=internal_price*load*self.dt #there is enough demand of engery on the grid
                    player.bill[time] += revenue
        

        else :   #if the offer is too consequent on the grid
            
            proportion_internal_demand=1
            proportion_internal_supply=internal_exchange/demand
            self.imbalance[0][time] = proportion_internal_demand
            self.imbalance[1][time] = proportion_internal_supply
            
            for idx,dico in self.players.items():
            
                player = dico["class"]
                
                
                load=player.load[time]

                if load>0: #if the player needs energy

                    cost=internal_price*load*self.dt  #there is enough energy produced on the grid
                    player.bill[time] += cost

                elif load<0:  #if the player supply energy

                    revenue= (internal_price*(proportion_internal_supply) + external_selling_price*(1-proportion_internal_supply))*load*self.dt
                            #the players pays in proportion of his supply
                    player.bill[time] += revenue
    



## Transmit data to the player

    def give_info(self,t):
        
        departure=[0]*4  #departure[i]=1 if the car i leaves the station at t
        arrival=[0]*4    #arrival[i]=1 if the car i arrives in the station at t
        
        for i in range(4):
            if t==self.scenario["planning"][0,i]:
                departure[i]=1
            if t==self.scenario["planning"][1,i]:
                arrival[i]=1
            
        
        data_scenario = { "sun" : self.scenario["sunshine"][t],"demand" : self.scenario["industrial demand"][t],"departures" : departure, "arrivals" : arrival}
        
    #the manager informs the price of the last slot
        prices = {"internal" : self.prices["internal"][t],"external_sale" : self.prices["external_sale"][t],"external_purchase" : self.prices["external_purchase"][t]}
            
            
            
        for idx,dico in self.players.items():
            
            player = dico["class"]
            
           
        player.observe(t,data_scenario,prices,{"proportion_internal_demand": self.imbalance[0][t],"proportion_internal_supply":self.imbalance[1][t]})
           



## Playing one party 

    def play(self):
        
        pv,ldem,planning=self.draw_random_scenario()
        
            
        for t in range(self.horizon): # main loop
            
            
            demand, supply = self.energy_balance(t)
            self.compute_bills(t, demand, supply)
            self.give_info(t)
    
    def reset(self):
        #reset the attributes of the manager
        self.imbalance=np.zeros((2,self.horizon))
        self.scenario={"planning":np.zeros((2,4)),"sunshine":np.zeros(self.horizon),"industrial demand":np.zeros(self.horizon)}
        
        for idx,dico in self.players.items(): #reset the attributes of thes players
            
            player = dico["class"]
            player.reset() 
    
    
    
    def simulate(self,nb_simulation):
        
        
        tab_load=np.zeros((self.nb_tot_players,nb_simulation,self.horizon))  #player,day,slot
        tab_bill=np.zeros((self.nb_tot_players,nb_simulation,self.horizon))  #player,day,slot
        
        tab_price={"internal" : np.zeros((nb_simulation,self.horizon)), "external_purchase" : np.zeros((nb_simulation,self.horizon)), "external_sale" : np.zeros((nb_simulation,self.horizon))}  #day,slot
        
        
        tab_battery_stock_IC_SF = np.zeros((self.nb_players["industrial_consumer"]+self.nb_players["industrial_consumer"],nb_simulation,self.horizon+1)) #player,day,slot
        
        tab_battery_stock_CS = np.zeros((self.nb_players["charging_station"],nb_simulation,4,self.horizon+1)) #player,day,slot
        
        tab_scenario= {"planning":np.zeros((nb_simulation,2,4)),"sunshine":np.zeros((nb_simulation,self.horizon)),"industrial demand":np.zeros((nb_simulation,self.horizon))} #day,departure/arrival,voiture #day,slot #day,slot
        
        tab_grid_load=np.zeros((2,nb_simulation,self.horizon))  #sale/purchase,day,slot
        
        tab_imbalance = np.zeros((nb_simulation,2,self.horizon)) #day,sale/purchase,slot
        
        for i in range(nb_simulation):
                    
            self.play()
            
            tab_grid_load[0,i]=self.grid_load["demand"]
            tab_grid_load[1,i]=self.grid_load["supply"]
            
            for type in ["planning","sunshine","industrial demand"]:
                tab_scenario[type][i]=self.scenario[type]
            
            for type in ["internal","external_purchase","external_sale"]:
                tab_price[type][i]=self.prices[type]
                    
            tab_imbalance[i] = self.imbalance
            
            for idx,dico in self.players.items():
            
                player = dico["class"]
                
                
                tab_load[int(idx), i, :] = player.load
                tab_bill[int(idx), i, :] = player.bill
                
                if dico["type"]=="charging_station":
                    
                    new_bat = np.concatenate((player.battery_stock["slow"],player.battery_stock["fast"]),axis=1)
                    
                    new_bat = np.transpose(new_bat)
                    
                    tab_battery_stock_CS[int(idx)-self.nb_players["industrial_consumer"]-self.nb_players["industrial_consumer"],i,:,:] = new_bat
                else:
                    tab_battery_stock_IC_SF[int(idx),i,:] = player.battery_stock
                    
                
            
            
            self.reset()
            
            
        np.save("data_visualize/imbalance simulation",tab_imbalance)
        np.save("data_visualize/load simulation",tab_load)
        np.save("data_visualize/bill simulation",tab_bill)
        np.save("data_visualize/price simulation",np.array([tab_price]))
        np.save("data_visualize/battery stock simulation IC SF",tab_battery_stock_IC_SF)
        np.save("data_visualize/battery stock simulation CS",tab_battery_stock_CS)
        np.save("data_visualize/scenario simulation",np.array([tab_scenario]))
        np.save("data_visualize/grid load simulation",tab_grid_load)
        

