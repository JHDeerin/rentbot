# Design Notes

## Automating Rent Amount entry

Right now, Mr. Rentbot does a fine job of keeping track of our basic rental needs, but there're still some manual steps that it doesn't take care of for us yet. In particular, there are 2 big ones that prevent us from setting up all our rental info once and then never having to touch it again[*](until-someone-moves-out-slash-in-slash-dies-slash-etc):

1.  Entering the rent/utility/etc. amounts we owe our various service providers for the month, and
2.  Actually requesting/sending payments from everyone's bank accounts.

#2 is trickier because it involves finding a free API that lets us transer actual money (which was tricky to find the admittedly-brief last time I checked about a year ago), and there's an argument to intentionally requiring everyone to pay manually/etc. So for now, let's focus on automating the rent-getting

### The Current, Manual Process

The first step to automating a process is to have a process to automate (preferably an optimized one with a minimal number of simple steps). So, what's the current process?

Basically, we have our main base rent (from our apartment's landlord) + a few utility bills from different providers - I need to check each service, see when they post their bill, and then add the total bill cost to rentbot. Let's see what this looks like for September 2023 (checking our bill on `2023-10-09`):

1.  Log in to our [apartment website](https://centennialplaceapartments.securecafe.com/residentservices/centennial-place/userlogin.aspx#tab_PaymentAccounts)
    1.  Go to the "Recent Activity" tab and find all the payments for the first day of the current month (e.g. `10/1/2023`). Typically, there are 2 important ones - `GPR - Market` will have the base monthly rent for our apartment (which should stay constant throughout our lease, but can potentially go up when we renew), and `Pre-Authorized Payment` (which is the total payment they've charged to our account for the month). So, we can just look at `Pre-Authorized Payment` to get the total amount due from the apartment directly, or get the utilities amount they've charged us (sewer, water, trash disposal, etc.) as `Utility Cost = (Pre-Authorized Payment) - (GPR - Market)`
    2.  Since we currently split up rent into 2 columns - base rent and utilities - save the GPR Market rate ($1816) and utility amount ($84.97) separately
2.  Log into [Comcast Xfinity](https://customer.xfinity.com/billing/services) to view our internet bill
    1.  The `Total Balance` field is usually just the balance for the past month, but to be sure, go to the `Statement History` and find the row with the past month in it (e.g. `Aug 26 - Sep 25` will be the bill for September) - copy that amount ($95)
3.  Log in to the [Southern Company](https://customerservice2.southerncompany.com/Login) to view our electricity bill
    -   This login is fiddly and unintuitive and semi-broken, and so it's usually much easier for me to check it via email - looking for the latest email called `View your latest Georgia Power bill` from `g2georgiaapps@southernco.com` and getting the bill amount from there ($206.83)
4.  Add up the amounts to get the total rent and total utility amount - in this case, $1816.00 for rent and ($84.97 + $95 + $206.83) = $386.80 for utilities.
    -   I'll normally add this up on a calculator, because I'm a programmer who traded mental math skills for silicon long ago
5.  Enter the rent amounts separately into rentbot using the `/rent rent-amt 1816.00` and `/rent utility-amt 386.80`
6.  Optionally, display the rent in the GroupMe with `/rent show`
7.  Optionally, mark that I've already paid the rent with `/rent paid`

So, summarizing, the process is basically this:

1.  For each website that has billing information for the month,
    1.  Log in to the website
    2.  Navigate to wherever the relevent bill(s) are and get all the payment info
    3.  Add each relevant payment to the "Rent" or "Utility" payment total
2.  Enter the rent amounts to Rentbot

This is pretty much the minimal process I can imagine - we need to get the billing info from somewhere, and then we need to enter it into Rentbot somehow.

### How do we Automate This?

Alright, we've got the process, now we need to figure out how to automate this.

First, let's focus on trying to get the rent info. At a minimum the info we need for this is a list of each website, the required login for that website (let's assume just a username and password for now, although who knows how 2-factor auth/etc. could throw this for a loop), and what part of the website to actually scrape the data from to get the rent + utility info.

I think a good, initial goal is to create a script I can run that'll print out the rent and utility amounts I owe. I'll definitely need to break that into smaller tasks, but let's start with that.
